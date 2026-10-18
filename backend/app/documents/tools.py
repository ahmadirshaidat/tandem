from fastapi import HTTPException
from pydantic import Field

from app.documents import service as svc
from app.memory.retrieval import SearchInput, search
from app.tasks.schemas import StrictInput


class GetDocument(StrictInput):
    document_id: str = Field(min_length=36, max_length=36)


class RetrieveDocuments(StrictInput):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)


class SuggestEdit(GetDocument):
    expected_text: str = Field(min_length=1, max_length=4000)
    replacement: str = Field(max_length=4000)
    reason: str = Field(min_length=1, max_length=1000)
    from_anchor: str = Field(default="", max_length=2000)
    to_anchor: str = Field(default="", max_length=2000)


def read(db, run, name, args):
    if name == "get_document":
        d = svc.shared_access(
            db, run.workspace_id, args.document_id, run.requester_id, run.channel_id
        )
        svc.audit(
            db,
            run.workspace_id,
            "agent",
            run.workspace_id,
            "document.agent_read",
            "document",
            d.id,
            request_id=run.request_id,
        )
        return {
            "id": d.id,
            "title": d.title,
            "text": d.plain_text[:10000],
            "headings": [line for line in d.markdown.splitlines() if line.startswith("#")][:40],
            "source": {"type": "document", "id": d.id},
            "trust": "UNTRUSTED DATA",
        }
    from app.agent.service import allowed_channels

    return search(
        db,
        run.workspace_id,
        run.requester_id,
        SearchInput(query=args.query, source_type="document", limit=args.limit),
        channel_ids=[
            c.id for c in allowed_channels(db, run.workspace_id, run.requester_id, run.channel_id)
        ],
    )


def validate_suggestion(db, wid, uid, parsed, creation=False):
    d = svc.document(db, wid, parsed.document_id, uid)
    data = parsed.model_dump(mode="json")
    if creation:
        anchors = svc.transform(d.state, action="anchor", expected_text=parsed.expected_text)
        data.update(from_anchor=anchors["from_anchor"], to_anchor=anchors["to_anchor"])
    if not data["from_anchor"] or not data["to_anchor"]:
        raise HTTPException(422, "Suggestion anchors required")
    return data, {}


def apply(db, p, uid):
    d = svc.document(db, p.workspace_id, p.payload["document_id"], uid, "editor", lock=True)
    value = svc.transform(
        d.state,
        action="apply",
        **{k: p.payload[k] for k in ["from_anchor", "to_anchor", "expected_text", "replacement"]},
    )
    if value.get("stale"):
        return None
    import base64

    update = base64.b64decode(value["state"])
    # This is a server-generated full CRDT update, bounded by document size rather than frame size.
    prior = svc.settings.document_update_bytes
    if len(update) > prior:
        raise HTTPException(413, "Suggestion update is too large")
    svc.persist(db, d, uid, update, snapshot_actor="agent_approved", proposal_id=p.id)
    svc.log(db, d, uid, "suggestion_accepted", proposal_id=p.id)
    return {"task_ids": [], "comment_ids": [], "document_ids": [d.id]}
