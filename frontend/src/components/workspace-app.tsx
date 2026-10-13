"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleCheck,
  Copy,
  FolderPlus,
  Home,
  LogOut,
  Plus,
  Settings,
  ShieldCheck,
  UserPlus,
  Users,
  Sparkles,
} from "lucide-react";
import { ErrorNotice, Field, Logo, ThemeToggle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { AITrialPage } from "@/components/ai-trial";
import {
  api,
  ApiError,
  post,
  roleLabels,
  type Invitation,
  type Member,
  type Role,
  type User,
  type Workspace,
} from "@/lib/api";

type Section = "home" | "members" | "settings" | "new" | "ai";
const nav = [
  { href: "/", section: "home", label: "Getting started", Icon: Home },
  { href: "/members", section: "members", label: "Members", Icon: Users },
  { href: "/settings", section: "settings", label: "Settings", Icon: Settings },
  { href: "/ai", section: "ai", label: "Try AI", Icon: Sparkles },
];
function subscribeSelection(callback: () => void) {
  window.addEventListener("tandem-workspace", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("tandem-workspace", callback);
    window.removeEventListener("storage", callback);
  };
}
function selectWorkspace(userId: string, id: string) {
  localStorage.setItem(`tandem-workspace:${userId}`, id);
  window.dispatchEvent(new Event("tandem-workspace"));
}
export function WorkspaceApp({ section }: { section: Section }) {
  const router = useRouter();
  const client = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
  });
  const workspaces = useQuery({
    queryKey: ["workspaces", me.data?.id],
    queryFn: () => api<Workspace[]>("/workspaces"),
    enabled: !!me.data,
  });
  const chosenId = useSyncExternalStore(
    subscribeSelection,
    () =>
      me.data ? localStorage.getItem(`tandem-workspace:${me.data.id}`) : null,
    () => null,
  );
  const workspace =
    workspaces.data?.find((item) => item.id === chosenId) ??
    workspaces.data?.[0];
  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      client.clear();
      router.replace("/login");
    },
  });
  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401)
      router.replace("/login");
  }, [me.error, router]);
  if (
    me.isPending ||
    (!!me.data && workspaces.isPending) ||
    (me.error instanceof ApiError && me.error.status === 401)
  )
    return (
      <div role="status" className="loading">
        Opening your workspace…
      </div>
    );
  if (me.error || workspaces.error || !me.data)
    return (
      <main className="empty">
        <h1>We couldn’t open your workspace.</h1>
        <ErrorNotice error={me.error ?? workspaces.error} />
        <Button
          onClick={() => {
            void me.refetch();
            void workspaces.refetch();
          }}
        >
          Try again
        </Button>
      </main>
    );
  const user = me.data;
  const picker = (id: string) => (
    <div className="workspace-picker">
      <Label htmlFor={id}>Workspace</Label>
      <select
        id={id}
        className="input"
        aria-label="Switch workspace"
        value={workspace?.id ?? ""}
        onChange={(event) => selectWorkspace(user.id, event.target.value)}
      >
        {!workspaces.data?.length && <option value="">No workspace yet</option>}
        {workspaces.data?.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </div>
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        {picker("desktop-workspace-select")}
        <Button asChild variant="ghost">
          <Link href="/workspaces/new">
            <Plus size={16} /> New workspace
          </Link>
        </Button>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {nav.map(({ href, section: key, label, Icon }) => (
            <Link
              className="nav-item"
              key={key}
              href={href}
              aria-current={section === key ? "page" : undefined}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <ThemeToggle />
          <div className="row sidebar-user">
            <span className="avatar">
              {user.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <div className="sidebar-user-name">{user.name}</div>
              <div className="text-small text-muted">{user.email}</div>
            </div>
          </div>
          <Button
            variant="ghost"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <LogOut size={16} /> Log out
          </Button>
          <ErrorNotice error={logout.error} />
        </div>
      </aside>
      <main className="main-panel">
        <header className="app-header row-between">
          <Logo />
          <div className="row">
            <span className="chip">
              {workspace ? roleLabels[workspace.role] : "Your account"}
            </span>
            <ThemeToggle />
          </div>
        </header>
        <div className="content">
          <div className="mobile-workspace">
            {picker("mobile-workspace-select")}
            <div className="row-between">
              <Link href="/workspaces/new" className="button button-ghost">
                <Plus size={16} /> New workspace
              </Link>
              <Button
                variant="ghost"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
              >
                <LogOut size={16} /> Log out
              </Button>
            </div>
            <ErrorNotice error={logout.error} />
          </div>
          {section === "new" ? (
            <CreateWorkspace user={user} />
          ) : !workspace ? (
            <NoWorkspace />
          ) : section === "members" ? (
            <Members key={workspace.id} workspace={workspace} user={user} />
          ) : section === "ai" ? (
            <AITrialPage key={workspace.id} workspace={workspace} />
          ) : section === "settings" ? (
            <WorkspaceSettings
              key={`${workspace.id}:${workspace.name}`}
              workspace={workspace}
            />
          ) : (
            <GettingStarted workspace={workspace} user={user} />
          )}
        </div>
      </main>
      <nav className="mobile-tabs" aria-label="Main navigation">
        {nav.map(({ href, section: key, label, Icon }) => (
          <Link
            className="nav-item"
            key={key}
            href={href}
            aria-current={section === key ? "page" : undefined}
          >
            <Icon size={20} />
            {key === "home" ? "Home" : label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
function NoWorkspace() {
  return (
    <div className="empty">
      <span className="icon-circle">
        <FolderPlus />
      </span>
      <h1>Your team starts here.</h1>
      <p>Create your first workspace, then invite the people you build with.</p>
      <Button asChild>
        <Link href="/workspaces/new">
          <Plus size={16} /> Create workspace
        </Link>
      </Button>
    </div>
  );
}
function CreateWorkspace({ user }: { user: User }) {
  const router = useRouter();
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (form: FormData) =>
      api<Workspace>("/workspaces", post({ name: form.get("name") })),
    onSuccess: async (workspace) => {
      selectWorkspace(user.id, workspace.id);
      await client.invalidateQueries({ queryKey: ["workspaces"] });
      router.push("/");
    },
  });
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">A PLACE OF YOUR OWN</div>
        <h1>Create your workspace.</h1>
        <p>One shared space for your team. You’ll be its first Owner.</p>
      </div>
      <div className="card form-card card-body">
        <ErrorNotice error={mutation.error} />
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(new FormData(event.currentTarget));
          }}
        >
          <Field
            label="Workspace name"
            id="workspace-name"
            name="name"
            placeholder="e.g. Studio North"
            required
            minLength={1}
            maxLength={80}
            help="Use a team or company name. You can change it later."
          />
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Creating…" : "Create workspace"}
            <ArrowRight size={16} />
          </Button>
        </form>
      </div>
    </>
  );
}
function GettingStarted({
  workspace,
  user,
}: {
  workspace: Workspace;
  user: User;
}) {
  const members = useQuery({
    queryKey: ["members", workspace.id],
    queryFn: () => api<Member[]>(`/workspaces/${workspace.id}/members`),
  });
  const canManage = ["owner", "admin"].includes(workspace.role);
  return (
    <>
      <div className="page-heading row-between">
        <div>
          <div className="eyebrow">{workspace.name}</div>
          <h1>A good place to begin.</h1>
          <p>
            Welcome, {user.name.split(" ")[0]}. Let’s bring your people
            together.
          </p>
        </div>
        <span className="chip chip-agent">
          <CircleCheck size={14} /> Workspace created
        </span>
      </div>
      <div className="welcome">
        <div>
          <span className="chip chip-brand">Your team, your workspace</span>
          <h2 style={{ marginTop: 20 }}>
            Great work starts
            <br />
            with the right people.
          </h2>
          <p className="text-muted">
            Invite your teammates and give everyone the access they need. You’re
            building this together.
          </p>
          <Button asChild>
            <Link href="/members">
              <UserPlus size={16} />
              {canManage ? "Invite your team" : "Meet your team"}
            </Link>
          </Button>
        </div>
        <div className="welcome-art" aria-hidden="true">
          <div className="card">
            <div className="row">
              <span className="avatar">
                {workspace.name.slice(0, 2).toUpperCase()}
              </span>
              <strong>{workspace.name}</strong>
            </div>
            <div className="mini-line" />
            <div className="mini-line" style={{ width: "70%" }} />
            <div className="row" style={{ marginTop: 20 }}>
              <span className="chip chip-agent">
                <Check size={14} /> Ready to connect
              </span>
            </div>
          </div>
        </div>
      </div>
      <ErrorNotice error={members.error} />
      <div className="onboarding-grid">
        <div className="card onboarding-card">
          <span className="icon-circle">
            <Users />
          </span>
          <h3>Bring everyone into the loop.</h3>
          <p>
            {members.data
              ? `${members.data.length} ${members.data.length === 1 ? "person has" : "people have"} joined ${workspace.name}.`
              : "Loading your team…"}{" "}
            Give each teammate a role that fits how they work.
          </p>
          <Button asChild variant="secondary">
            <Link href="/members">
              View members <ChevronRight size={16} />
            </Link>
          </Button>
        </div>
        <div className="card onboarding-card">
          <span className="icon-circle">
            <ShieldCheck />
          </span>
          <h3>Make it feel like your team.</h3>
          <p>
            A clear workspace name and the right permissions help everyone feel
            at home.
          </p>
          <Button asChild variant="secondary">
            <Link href="/settings">
              Workspace settings <ChevronRight size={16} />
            </Link>
          </Button>
        </div>
      </div>
    </>
  );
}
function WorkspaceSettings({ workspace }: { workspace: Workspace }) {
  const client = useQueryClient();
  const [saved, setSaved] = useState(false);
  const canManage = ["owner", "admin"].includes(workspace.role);
  const mutation = useMutation({
    mutationFn: (form: FormData) =>
      api(`/workspaces/${workspace.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: form.get("name") }),
      }),
    onSuccess: async () => {
      setSaved(true);
      await client.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">WORKSPACE SETTINGS</div>
        <h1>A little more yours.</h1>
        <p>Manage the basics for {workspace.name}.</p>
      </div>
      <div className="card card-body form-card">
        <h2>General</h2>
        <p className="text-muted">
          Your workspace name is visible to everyone on your team.
        </p>
        <ErrorNotice error={mutation.error} />
        {saved && (
          <div role="status" className="notice">
            Workspace updated.
          </div>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setSaved(false);
            mutation.mutate(new FormData(event.currentTarget));
          }}
        >
          <Field
            label="Workspace name"
            id="settings-name"
            name="name"
            defaultValue={workspace.name}
            required
            maxLength={80}
            disabled={!canManage}
          />
          <Button type="submit" disabled={!canManage || mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save changes"}
          </Button>
          {!canManage && (
            <p className="text-small text-muted" style={{ marginTop: 16 }}>
              An Admin or Owner can update workspace settings.
            </p>
          )}
        </form>
      </div>
    </>
  );
}
function PermissionMatrix() {
  const rows = [
    { name: "View workspace and members", values: [true, true, true] },
    { name: "Invite and manage members", values: [true, false, false] },
    { name: "Change workspace settings", values: [true, false, false] },
  ];
  return (
    <>
      <div className="section-heading">
        <h2>A role for every kind of teammate.</h2>
        <p className="text-muted">
          Owners manage ownership. Admins manage the team. Editors and Viewers
          cannot change members or roles.
        </p>
      </div>
      <div className="card table-scroll">
        <table className="permission-table">
          <caption className="sr-only">Workspace role permissions</caption>
          <thead>
            <tr>
              <th scope="col">Permission</th>
              <th scope="col">Owner / Admin</th>
              <th scope="col">Editor / Developer</th>
              <th scope="col">Viewer</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                {row.values.map((allowed, index) => (
                  <td key={index}>
                    {allowed ? (
                      <span className="chip chip-success">
                        <Check size={14} />
                        Allowed
                      </span>
                    ) : (
                      <span className="text-muted">
                        —<span className="sr-only">Not allowed</span>
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
function Members({ workspace, user }: { workspace: Workspace; user: User }) {
  const client = useQueryClient();
  const canManage = ["owner", "admin"].includes(workspace.role);
  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);
  const [inviteLink, setInviteLink] = useState("");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<Error | null>(null);
  const members = useQuery({
    queryKey: ["members", workspace.id],
    queryFn: () => api<Member[]>(`/workspaces/${workspace.id}/members`),
  });
  const invitations = useQuery({
    queryKey: ["invitations", workspace.id],
    queryFn: () => api<Invitation[]>(`/workspaces/${workspace.id}/invitations`),
    enabled: canManage,
  });
  const invalidate = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["members", workspace.id] }),
      client.invalidateQueries({ queryKey: ["invitations", workspace.id] }),
      client.invalidateQueries({ queryKey: ["workspaces"] }),
    ]);
  };
  const changeRole = useMutation({
    mutationFn: ({ member, role }: { member: Member; role: Role }) =>
      api(`/workspaces/${workspace.id}/members/${member.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (member: Member) =>
      api(`/workspaces/${workspace.id}/members/${member.id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      setRemoveTarget(null);
      await invalidate();
    },
  });
  const invite = useMutation({
    mutationFn: (form: FormData) =>
      api<Invitation>(
        `/workspaces/${workspace.id}/invitations`,
        post({ email: form.get("email"), role: form.get("role") }),
      ),
    onSuccess: async (data) => {
      setInviteLink(data.invite_url ?? "");
      setCopied(false);
      await invalidate();
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      api(`/workspaces/${workspace.id}/invitations/${id}`, {
        method: "DELETE",
      }),
    onSuccess: invalidate,
  });
  async function copy() {
    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopied(true);
      setCopyError(null);
    } catch {
      setCopyError(
        new Error(
          "Copy isn’t available here. Select and copy the invitation link below.",
        ),
      );
    }
  }
  const ownerCount =
    members.data?.filter((item) => item.role === "owner").length ?? 0;
  return (
    <>
      <div className="page-heading row-between">
        <div>
          <div className="eyebrow">{workspace.name} / PEOPLE</div>
          <h1>Your people. In one place.</h1>
          <p>Build a team where everyone knows their role.</p>
        </div>
        <span className="chip">{members.data?.length ?? "…"} members</span>
      </div>
      <ErrorNotice error={members.error ?? changeRole.error ?? revoke.error} />
      {canManage ? (
        <div className="card card-body" style={{ marginBottom: 24 }}>
          <h2>Invite someone to the team.</h2>
          <p className="text-muted">
            Create a personal link, then share it with your teammate. It expires
            in 7 days.
          </p>
          <ErrorNotice error={invite.error} />
          <form
            className="invite-form"
            onSubmit={(event) => {
              event.preventDefault();
              invite.mutate(new FormData(event.currentTarget));
            }}
          >
            <Field
              label="Their email address"
              id="invite-email"
              name="email"
              type="email"
              required
              placeholder="teammate@yourteam.com"
            />
            <div className="field">
              <Label htmlFor="invite-role">Role</Label>
              <select
                id="invite-role"
                name="role"
                className="input"
                defaultValue="editor"
              >
                <option value="editor">Editor / Developer</option>
                <option value="admin">Admin</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <Button type="submit" disabled={invite.isPending}>
              <UserPlus size={16} />
              {invite.isPending ? "Creating…" : "Create invitation"}
            </Button>
          </form>
          {inviteLink && (
            <>
              <div
                role="status"
                className="notice"
                style={{ marginTop: 20, marginBottom: 0 }}
              >
                Invitation created. Share this link with your teammate.
              </div>
              <div className="invite-link">
                <div>
                  <Label htmlFor="invite-link">Invitation link</Label>
                  <input
                    className="input"
                    id="invite-link"
                    readOnly
                    value={inviteLink}
                    onFocus={(event) => event.currentTarget.select()}
                  />
                </div>
                <Button variant="secondary" onClick={() => void copy()}>
                  <Copy size={16} />
                  {copied ? "Copied" : "Copy link"}
                </Button>
              </div>
              <ErrorNotice error={copyError} />
            </>
          )}
        </div>
      ) : (
        <div className="notice">
          An Admin or Owner can invite teammates and manage roles.
        </div>
      )}
      <div className="card table-scroll">
        <div
          className="member-table"
          role="table"
          aria-label="Workspace members"
        >
          <div className="table-row table-head" role="row">
            <span role="columnheader">Member</span>
            <span role="columnheader">Role</span>
            <span role="columnheader">Actions</span>
          </div>
          {members.isPending && (
            <p role="status" className="card-body text-muted">
              Loading members…
            </p>
          )}
          {members.data?.map((member) => {
            const protectedOwner =
              member.role === "owner" &&
              (workspace.role !== "owner" || ownerCount <= 1);
            const canEdit = canManage && !protectedOwner;
            return (
              <div className="table-row" role="row" key={member.id}>
                <div role="cell" className="row">
                  <span className="avatar">
                    {member.name.slice(0, 2).toUpperCase()}
                  </span>
                  <div>
                    <div className="member-name">
                      {member.name}
                      {member.user_id === user.id ? " (you)" : ""}
                    </div>
                    <div className="text-small text-muted">{member.email}</div>
                  </div>
                </div>
                <div role="cell">
                  {canEdit ? (
                    <>
                      <Label htmlFor={`role-${member.id}`} className="sr-only">
                        Role for {member.name}
                      </Label>
                      <select
                        id={`role-${member.id}`}
                        className="input role-select"
                        value={member.role}
                        disabled={changeRole.isPending || remove.isPending}
                        onChange={(event) =>
                          changeRole.mutate({
                            member,
                            role: event.target.value as Role,
                          })
                        }
                      >
                        {Object.entries(roleLabels)
                          .filter(
                            ([role]) =>
                              role !== "owner" || workspace.role === "owner",
                          )
                          .map(([role, label]) => (
                            <option key={role} value={role}>
                              {label}
                            </option>
                          ))}
                      </select>
                    </>
                  ) : (
                    <span className="chip chip-brand">
                      {roleLabels[member.role]}
                    </span>
                  )}
                </div>
                <div role="cell">
                  {canEdit ? (
                    <Button
                      variant="ghost"
                      aria-label={`Remove ${member.name}`}
                      onClick={() => {
                        remove.reset();
                        setRemoveTarget(member);
                      }}
                    >
                      Remove
                    </Button>
                  ) : (
                    <span className="text-small text-muted">
                      {protectedOwner && ownerCount <= 1 ? "Last Owner" : "—"}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {canManage && (
        <>
          <div className="section-heading">
            <h2>Invitations</h2>
            <p className="text-muted">
              Only the invited email address can use each link.
            </p>
          </div>
          <div className="card card-body">
            <ErrorNotice error={invitations.error} />
            {invitations.isPending ? (
              <p role="status">Loading invitations…</p>
            ) : !invitations.data?.length ? (
              <p className="text-muted" style={{ margin: 0 }}>
                No invitations yet. Your next teammate could be one link away.
              </p>
            ) : (
              invitations.data.map((item) => (
                <div className="invitation-item" key={item.id}>
                  <div>
                    <div className="member-name">{item.email}</div>
                    <div className="text-small text-muted">
                      {roleLabels[item.role]} · Expires{" "}
                      {new Date(item.expires_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="row">
                    <span
                      className={`chip ${item.status === "accepted" ? "chip-success" : "chip-warning"}`}
                    >
                      {item.status}
                    </span>
                    {item.status === "pending" && (
                      <Button
                        variant="ghost"
                        disabled={revoke.isPending}
                        onClick={() => revoke.mutate(item.id)}
                      >
                        Revoke
                      </Button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}
      <PermissionMatrix />
      <ConfirmDialog
        open={!!removeTarget}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setRemoveTarget(null);
        }}
        title={`Remove ${removeTarget?.name ?? "member"}?`}
        description="They’ll lose access to this workspace. You can invite them again later."
      >
        <ErrorNotice error={remove.error} />
        <Button
          variant="secondary"
          disabled={remove.isPending}
          onClick={() => setRemoveTarget(null)}
        >
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => removeTarget && remove.mutate(removeTarget)}
        >
          {remove.isPending ? "Removing…" : "Remove member"}
        </Button>
      </ConfirmDialog>
    </>
  );
}
