from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from sqlalchemy import func, select
from test_channels import channel, path, send
from test_workspaces import add_member, workspace

from app.channels.models import Channel
from app.tasks.models import TaskActivity, WorkspaceTaskState


def project(owner, wid, name="Web app", key="WEB"):
    response = owner.post(f"/api/workspaces/{wid}/projects", json={"name": name, "key": key})
    assert response.status_code == 201, response.text
    return response.json()


def task(owner, wid, pid, title="A task", **extra):
    response = owner.post(
        f"/api/workspaces/{wid}/tasks", json={"project_id": pid, "title": title, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def task_path(wid, tid):
    return f"/api/workspaces/{wid}/tasks/{tid}"


def test_projects_roles_task_fields_activity_and_comments(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    editor, _ = add_member(owner, client_factory, wid, "editor@example.com", "editor")
    viewer, _ = add_member(owner, client_factory, wid, "viewer@example.com", "viewer")
    pid = project(owner, wid)["id"]
    assert (
        editor.post(f"/api/workspaces/{wid}/projects", json={"name": "No", "key": "NO"}).status_code
        == 403
    )
    first = task(
        editor,
        wid,
        pid,
        type="bug",
        description="**safe** <script>text</script>",
        priority="P1",
        due_date="2026-10-20",
    )
    assert first["key"] == "BUG-1" and first["created_by_agent"] is False and first["version"] == 1
    assert viewer.get(task_path(wid, first["id"])).status_code == 200
    changed = editor.patch(
        task_path(wid, first["id"]),
        json={
            "version": 1,
            "title": "Changed",
            "priority": "P3",
            "due_date": None,
            "assignee_id": first["reporter"]["id"],
            "type": "task",
        },
    )
    assert changed.status_code == 200, changed.text
    latest = changed.json()
    assert latest["key"] == "BUG-1" and latest["type"] == "task" and latest["due_date"] is None
    activities = owner.get(task_path(wid, first["id"]) + "/activity").json()["activity"]
    assert {a["field"] for a in activities} == {
        "task",
        "title",
        "priority",
        "due_date",
        "assignee_id",
        "type",
    }
    priority = next(a for a in activities if a["field"] == "priority")
    assert (
        priority["old_value"] == "P1"
        and priority["new_value"] == "P3"
        and priority["actor"]["id"] == first["reporter"]["id"]
    )
    comment = editor.post(task_path(wid, first["id"]) + "/comments", json={"body": "A question"})
    assert comment.status_code == 201
    cid = comment.json()["id"]
    assert (
        owner.patch(
            task_path(wid, first["id"]) + f"/comments/{cid}", json={"body": "No", "version": 1}
        ).status_code
        == 403
    )
    assert (
        editor.patch(
            task_path(wid, first["id"]) + f"/comments/{cid}", json={"body": "Edited", "version": 1}
        ).status_code
        == 200
    )
    assert owner.get(task_path(wid, first["id"])).json()["comment_count"] == 1
    assert (
        owner.delete(task_path(wid, first["id"]) + f"/comments/{cid}?version=2").status_code == 204
    )
    assert owner.get(task_path(wid, first["id"])).json()["comment_count"] == 0
    assert (
        editor.request(
            "DELETE", task_path(wid, first["id"]), json={"version": latest["version"]}
        ).status_code
        == 403
    )


def test_viewer_denied_every_task_mutation_and_read_only_project(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    viewer, _ = add_member(owner, client_factory, wid, "viewer@example.com", "viewer")
    pid = project(owner, wid)["id"]
    t = task(owner, wid, pid)
    base = task_path(wid, t["id"])
    checks = [
        ("POST", f"/api/workspaces/{wid}/tasks", {"project_id": pid, "title": "No"}),
        ("PATCH", base, {"version": 1, "title": "No"}),
        ("POST", base + "/move", {"version": 1, "status": "done"}),
        ("DELETE", base, {"version": 1}),
        ("POST", base + "/comments", {"body": "No"}),
        (
            "POST",
            f"/api/workspaces/{wid}/tasks/bulk",
            {"tasks": [{"id": t["id"], "version": 1}], "status": "done"},
        ),
        ("PATCH", f"/api/workspaces/{wid}/projects/{pid}", {"name": "No"}),
        ("DELETE", f"/api/workspaces/{wid}/projects/{pid}", None),
    ]
    for method, url, body in checks:
        response = viewer.request(method, url, json=body)
        assert response.status_code == 403, (method, url, response.text)
    assert viewer.get(f"/api/workspaces/{wid}/tasks").json()["total"] == 1


def test_concurrent_numbering_edits_and_moves(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    pid = project(owner, wid)["id"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = list(
            pool.map(
                lambda n: task(owner, wid, pid, f"Concurrent {n}", type="bug" if n % 2 else "task"),
                range(8),
            )
        )
    assert sorted(t["number"] for t in tasks) == list(range(1, 9))
    assert len({t["key"] for t in tasks}) == 8
    chosen = tasks[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        edits = list(
            pool.map(
                lambda title: owner.patch(
                    task_path(wid, chosen["id"]), json={"version": 1, "title": title}
                ),
                ["A", "B"],
            )
        )
    assert sorted(r.status_code for r in edits) == [200, 409]
    conflict = next(r.json() for r in edits if r.status_code == 409)
    assert conflict["error"]["details"]["kind"] == "task_conflict"
    assert conflict["error"]["details"]["current"]["version"] == 2
    with ThreadPoolExecutor(max_workers=2) as pool:
        moves = list(
            pool.map(
                lambda status: owner.post(
                    task_path(wid, chosen["id"]) + "/move", json={"version": 2, "status": status}
                ),
                ["in_progress", "done"],
            )
        )
    assert sorted(r.status_code for r in moves) == [200, 409]
    current = owner.get(task_path(wid, chosen["id"])).json()
    assert current["status"] in {"in_progress", "done"} and current["version"] == 3
    assert (
        db.scalar(
            select(WorkspaceTaskState.last_number).where(WorkspaceTaskState.workspace_id == wid)
        )
        == 8
    )


def test_ordering_single_card_move_pagination_filters_bulk_and_rollback(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    pid = project(owner, wid)["id"]
    tasks = [
        task(owner, wid, pid, f"Title {n}", priority="P1" if n % 2 else "P2") for n in range(6)
    ]
    ranks = {t["id"]: t["rank"] for t in tasks}
    last = tasks[-1]
    moved = owner.post(
        task_path(wid, last["id"]) + "/move",
        json={
            "version": 1,
            "status": "todo",
            "before_id": tasks[1]["id"],
            "after_id": tasks[0]["id"],
        },
    )
    assert moved.status_code == 200, moved.text
    rows = owner.get(f"/api/workspaces/{wid}/tasks?project_id={pid}").json()["tasks"]
    assert [t["id"] for t in rows] == [tasks[0]["id"], last["id"], *[t["id"] for t in tasks[1:-1]]]
    assert all(Decimal(t["rank"]) == Decimal(ranks[t["id"]]) for t in rows if t["id"] != last["id"])
    first = owner.get(f"/api/workspaces/{wid}/tasks?sort=number&limit=2").json()
    second = owner.get(
        f"/api/workspaces/{wid}/tasks?sort=number&limit=2&cursor={first['next_cursor']}"
    ).json()
    assert [t["number"] for t in first["tasks"] + second["tasks"]] == [1, 2, 3, 4]
    assert owner.get(f"/api/workspaces/{wid}/tasks?priority=P1").json()["total"] == 3
    assert owner.get(f"/api/workspaces/{wid}/tasks?text=Title%202").json()["total"] == 1
    bad = owner.post(
        f"/api/workspaces/{wid}/tasks/bulk",
        json={
            "tasks": [{"id": tasks[0]["id"], "version": 1}, {"id": last["id"], "version": 1}],
            "status": "done",
        },
    )
    assert bad.status_code == 409
    assert owner.get(task_path(wid, tasks[0]["id"])).json()["status"] == "todo"
    assert owner.get(f"/api/workspaces/{wid}/tasks?cursor=invalid").status_code == 422
    count = db.scalar(select(func.count()).select_from(TaskActivity))
    assert (
        owner.patch(
            task_path(wid, tasks[0]["id"]), json={"version": 1, "assignee_id": "not-a-member"}
        ).status_code
        == 404
    )
    assert db.scalar(select(func.count()).select_from(TaskActivity)) == count


def test_private_links_filtered_activity_and_cross_workspace(client_factory):
    owner, _ = client_factory("owner@example.com")
    outsider, _ = client_factory("outsider@example.com")
    wid = workspace(owner)["id"]
    other = workspace(outsider)["id"]
    viewer, _ = add_member(owner, client_factory, wid, "viewer@example.com", "viewer")
    pid = project(owner, wid)["id"]
    cid = channel(owner, wid, private=True)["id"]
    message = send(owner, path(wid, cid), "private message body")
    response = owner.post(
        f"/api/workspaces/{wid}/tasks/from-message",
        json={"project_id": pid, "title": "Shared task title", "message_id": message["id"]},
    )
    assert response.status_code == 201, response.text
    t = response.json()
    url = f"/api/workspaces/{wid}/links?object_type=task&object_id={t['id']}"
    link = owner.get(url).json()[0]
    assert link["target"]["url"] == f"/channels?channel={cid}&message={message['id']}"
    assert viewer.get(url).json() == []
    assert viewer.get(f"/api/workspaces/{wid}/links/{link['id']}").status_code == 404
    activities = viewer.get(task_path(wid, t["id"]) + "/activity").json()
    assert all(a["kind"] != "linked" for a in activities["activity"])
    assert message["id"] not in str(activities) and "private message body" not in str(activities)
    before = owner.get(f"/api/workspaces/{wid}/tasks").json()["total"]
    assert (
        viewer.post(
            f"/api/workspaces/{wid}/tasks/from-message",
            json={"project_id": pid, "title": "No", "message_id": message["id"]},
        ).status_code
        == 403
    )
    opid = project(outsider, other)["id"]
    ot = task(outsider, other, opid)
    for endpoint in [
        f"/projects/{opid}",
        f"/tasks/{ot['id']}",
        f"/tasks/{ot['id']}/comments",
        f"/tasks/{ot['id']}/activity",
    ]:
        assert owner.get(f"/api/workspaces/{other}" + endpoint).status_code == 404
        assert owner.get(f"/api/workspaces/{wid}" + endpoint).status_code == 404
    assert (
        owner.post(
            f"/api/workspaces/{wid}/links",
            json={
                "source_type": "task",
                "source_id": t["id"],
                "target_type": "task",
                "target_id": ot["id"],
                "version": t["version"],
            },
        ).status_code
        == 404
    )
    assert owner.get(f"/api/workspaces/{wid}/tasks").json()["total"] == before


def test_link_channel_project_archiving_soft_delete_and_member_unassign(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    editor, member = add_member(owner, client_factory, wid, "editor@example.com", "editor")
    pid = project(owner, wid)["id"]
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    assert (
        editor.patch(
            f"/api/workspaces/{wid}/channels/{cid}/project", json={"project_id": pid}
        ).status_code
        == 403
    )
    assert (
        owner.patch(
            f"/api/workspaces/{wid}/channels/{cid}/project", json={"project_id": pid}
        ).json()["project_id"]
        == pid
    )
    db.expire_all()
    assert db.get(Channel, cid).project_id == pid
    t = task(editor, wid, pid, assignee_id=member["user_id"])
    assert owner.delete(f"/api/workspaces/{wid}/members/{member['id']}").status_code == 204
    current = owner.get(task_path(wid, t["id"])).json()
    assert current["assignee_id"] is None and current["version"] == 2
    assert owner.request("DELETE", task_path(wid, t["id"]), json={"version": 2}).status_code == 204
    assert owner.get(task_path(wid, t["id"])).status_code == 404
    assert owner.get(f"/api/workspaces/{wid}/tasks").json()["total"] == 0
    new = task(owner, wid, pid)
    assert new["number"] == 2
    assert (
        owner.patch(f"/api/workspaces/{wid}/projects/{pid}", json={"archived": True}).status_code
        == 200
    )
    assert (
        owner.post(
            f"/api/workspaces/{wid}/tasks", json={"project_id": pid, "title": "No"}
        ).status_code
        == 409
    )
    assert owner.delete(f"/api/workspaces/{wid}/projects/{pid}").status_code == 409


def test_task_invalid_inputs_and_agent_flag_not_client_writable(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    pid = project(owner, wid)["id"]
    for extra in [
        {"title": " "},
        {"status": "invented"},
        {"created_by_agent": True},
        {"due_date": "nonsense"},
    ]:
        assert (
            owner.post(
                f"/api/workspaces/{wid}/tasks", json={"project_id": pid, "title": "Valid", **extra}
            ).status_code
            == 422
        )


def test_task_live_ordered_reconnect_privacy_and_revocation(client_factory):
    from test_channels import socket, until

    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    editor, member = add_member(owner, client_factory, wid, "editor@example.com", "editor")
    outsider, _ = client_factory("outsider@example.com")
    pid = project(owner, wid)["id"]
    watermark = owner.get(f"/api/workspaces/{wid}/tasks").json()["last_seq"]
    with socket(editor) as ws:
        ws.send_json({"type": "subscribe", "workspace_id": wid, "workspace_seq": watermark})
        first = task(owner, wid, pid)
        created = until(ws, "task.created")
        assert created["data"]["task"]["id"] == first["id"]
        assert created["seq"] == watermark + 1 and created["channel_id"] is None
        owner.post(task_path(wid, first["id"]) + "/move", json={"version": 1, "status": "done"})
        moved = until(ws, "task.moved")
        assert moved["seq"] == created["seq"] + 1
        owner.post(task_path(wid, first["id"]) + "/comments", json={"body": "Live comment"})
        commented = until(ws, "task.comment_created")
        assert commented["data"]["comment"]["body"] == "Live comment"
        assert commented["data"]["task"]["comment_count"] == 1
        cursor = commented["seq"]
    owner.patch(task_path(wid, first["id"]), json={"version": 3, "title": "Missed edit"})
    second = task(owner, wid, pid, "Missed create")
    private = channel(owner, wid, private=True, name="private-source")
    message = send(owner, path(wid, private["id"]), "SECRET BODY")
    owner.post(
        f"/api/workspaces/{wid}/links",
        json={
            "source_type": "task",
            "source_id": second["id"],
            "target_type": "message",
            "target_id": message["id"],
            "version": 1,
        },
    )
    with socket(editor) as ws:
        ws.send_json({"type": "subscribe", "workspace_id": wid, "workspace_seq": cursor})
        replay = [until(ws, kind) for kind in ["task.updated", "task.created", "task.updated"]]
        assert [row["seq"] for row in replay] == [cursor + 1, cursor + 2, cursor + 3]
        assert replay[0]["data"]["task"]["title"] == "Missed edit"
        assert all(
            message["id"] not in str(row)
            and "private-source" not in str(row)
            and "SECRET BODY" not in str(row)
            for row in replay
        )
        # The next event is new, proving the cursor did not replay duplicates.
        third = task(owner, wid, pid, "After replay")
        next_event = until(ws, "task.created")
        assert next_event["seq"] == cursor + 4 and next_event["data"]["task"]["id"] == third["id"]
        owner.delete(f"/api/workspaces/{wid}/members/{member['id']}")
        assert until(ws, "error")["data"]["code"] == "access_revoked"
    with socket(outsider) as ws:
        ws.send_json({"type": "subscribe", "workspace_id": wid, "workspace_seq": 0})
        assert until(ws, "error")["data"]["code"] == "access_denied"


def test_task_workspace_isolation_on_all_endpoints(client_factory):
    owner, _ = client_factory("owner@example.com")
    outsider, _ = client_factory("outsider@example.com")
    wid, other = workspace(owner)["id"], workspace(outsider)["id"]
    pid = project(owner, wid)["id"]
    first = task(owner, wid, pid)
    for root in [wid, other]:
        for method, suffix, body in [
            ("GET", "", None),
            ("PATCH", "", {"version": 1, "title": "Stolen"}),
            ("DELETE", "", {"version": 1}),
            ("POST", "/move", {"version": 1, "status": "done"}),
            ("GET", "/comments", None),
            ("POST", "/comments", {"body": "Stolen"}),
            ("GET", "/activity", None),
        ]:
            assert (
                outsider.request(
                    method, task_path(root, first["id"]) + suffix, json=body
                ).status_code
                == 404
            )
    assert outsider.get(f"/api/workspaces/{wid}/projects").status_code == 404
    assert outsider.get(f"/api/workspaces/{wid}/tasks").status_code == 404
