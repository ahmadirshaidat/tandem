"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  Copy,
  FolderPlus,
  LayoutGrid,
  Home,
  MessageSquare,
  LogOut,
  Plus,
  Settings,
  UserPlus,
  Users,
  Sparkles,
  Search,
  Database,
} from "lucide-react";
import { ErrorNotice, Field, Logo, ThemeToggle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ChannelNavigation, ChannelsPage } from "@/components/channel-room";
import { cached, clearChatCache, saveCache } from "@/lib/offline";
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

import { ApprovalsInbox } from "./proposals";
import { AgentSettingsPage, AuditLogPage } from "./agent";

import { SearchPage, MemorySettingsPage } from "./memory";

import { DocumentsPage } from "./documents";

type Section =
  | "home"
  | "members"
  | "settings"
  | "new"
  | "ai"
  | "channels"
  | "tasks"
  | "agent-settings"
  | "audit"
  | "inbox"
  | "search"
  | "memory"
  | "documents";
import { ProjectNavigation, TasksPage } from "@/components/tasks-page";

const nav = [
  {
    href: "/documents",
    section: "documents",
    label: "Documents",
    Icon: Database,
  },
  { href: "/search", section: "search", label: "Search", Icon: Search },
  {
    href: "/settings/memory",
    section: "memory",
    label: "Memory",
    Icon: Database,
  },
  {
    href: "/channels",
    section: "channels",
    label: "Chat",
    Icon: MessageSquare,
  },
  { href: "/tasks", section: "tasks", label: "Tasks", Icon: LayoutGrid },
  { href: "/inbox", section: "inbox", label: "Inbox", Icon: Check },
  { href: "/", section: "home", label: "Getting started", Icon: Home },
  { href: "/members", section: "members", label: "Members", Icon: Users },
  { href: "/settings", section: "settings", label: "Settings", Icon: Settings },
  { href: "/ai", section: "ai", label: "Try AI", Icon: Sparkles },
  {
    href: "/settings/agent",
    section: "agent-settings",
    label: "Agent settings",
    Icon: Sparkles,
  },
  {
    href: "/settings/audit",
    section: "audit",
    label: "Audit log",
    Icon: Settings,
  },
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
    queryFn: async () => {
      if (!navigator.onLine) {
        const bootstrap = cached<User>("account");
        if (bootstrap) return bootstrap.value;
      }
      const user = await api<User>("/auth/me");
      if (cached<User>("account")?.value.id !== user.id) clearChatCache();
      saveCache("account", user);
      return user;
    },
    networkMode: "always",
  });
  const workspaces = useQuery({
    queryKey: ["workspaces", me.data?.id],
    queryFn: async () => {
      if (!navigator.onLine) {
        const bootstrap = cached<Workspace[]>(`workspaces:${me.data?.id}`);
        if (bootstrap) return bootstrap.value;
      }
      const result = await api<Workspace[]>("/workspaces");
      saveCache(`workspaces:${me.data?.id}`, result);
      return result;
    },
    networkMode: "always",
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
      clearChatCache();
      client.clear();
      router.replace("/login");
    },
  });
  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      clearChatCache();
      router.replace("/login");
    }
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
      <Label htmlFor={id} className="sr-only">
        Workspace
      </Label>
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
    <div
      className={`app-shell ${section === "channels" ? "chat-shell" : ""} ${section === "tasks" ? "tasks-shell" : ""} ${section === "home" && workspace ? "app-shell-with-aside" : ""} ${section === "settings" || section === "members" ? "settings-shell" : ""}`}
    >
      <aside className="sidebar">
        {(section === "settings" || section === "members") && workspace ? (
          <Link href="/" className="workspace-back">
            <ChevronLeft size={18} />
            Back to {workspace.name}
          </Link>
        ) : (
          <div className="workspace-identity">
            <span className="workspace-avatar">
              {workspace?.name.slice(0, 1).toUpperCase() ?? "T"}
            </span>
            <div className="workspace-identity-text">
              {picker("desktop-workspace-select")}
              <span className="text-small text-muted">
                {workspace ? roleLabels[workspace.role] : "Your account"}
              </span>
            </div>
          </div>
        )}
        {(section === "settings" || section === "members") && (
          <div className="settings-workspace-picker">
            {picker("desktop-workspace-select")}
          </div>
        )}
        <Button asChild variant="ghost">
          <Link href="/workspaces/new">
            <Plus size={16} /> New workspace
          </Link>
        </Button>
        <nav className="sidebar-nav" aria-label="Main navigation">
          <div className="nav-group-label">Workspace</div>
          {nav.map(({ href, section: key, label, Icon }) => (
            <Link
              className="nav-item"
              key={key}
              href={href}
              aria-current={section === key ? "page" : undefined}
            >
              <Icon size={18} />
              {key === "settings" &&
              (section === "settings" || section === "members")
                ? "General"
                : label}
            </Link>
          ))}
        </nav>
        {workspace && (
          <ChannelNavigation
            workspace={workspace}
            user={user}
            choose={
              section === "channels"
                ? (id) =>
                    window.dispatchEvent(
                      new CustomEvent("tandem-channel", { detail: id }),
                    )
                : undefined
            }
          />
        )}
        {workspace && <ProjectNavigation workspace={workspace} user={user} />}
        <div className="sidebar-bottom">
          <Link href="/ai" className="sidebar-agent">
            <span className="agent-avatar">
              <Sparkles size={16} />
            </span>
            <span>
              <strong>Try AI</strong>
              <span className="text-small">Your AI teammate</span>
            </span>
          </Link>
          <div className="row sidebar-user">
            <span className="avatar">
              {user.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <div className="sidebar-user-name">{user.name}</div>
              <div className="text-small text-muted">
                {workspace ? roleLabels[workspace.role] : user.email}
              </div>
            </div>
            <ThemeToggle />
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
        <header className="app-header mobile-app-header row-between">
          {section === "settings" || section === "members" ? (
            <div className="row">
              <Link
                href="/"
                className="mobile-back"
                aria-label="Back to workspace"
              >
                <ChevronLeft size={20} />
              </Link>
              <h1>{section === "members" ? "Members" : "Settings"}</h1>
            </div>
          ) : (
            <Logo />
          )}
          <div className="row">
            <span className="chip">
              {workspace ? roleLabels[workspace.role] : "Your account"}
            </span>
            <ThemeToggle />
          </div>
        </header>
        {(section === "settings" || section === "members") && workspace && (
          <header className="settings-header">
            <h1>{section === "settings" ? "General" : "Members"}</h1>
            <p>
              {section === "settings"
                ? "Manage how your workspace looks and where it lives."
                : "Invite teammates and decide what each role can do."}
            </p>
          </header>
        )}
        <div
          className={`content ${section === "channels" ? "chat-content" : ""} ${section === "tasks" ? "tasks-content" : ""} ${section === "home" ? "home-content" : ""}`}
        >
          <details className="mobile-workspace">
            <summary>
              {workspace?.name ?? "Your account"}
              <ChevronDown size={16} />
            </summary>
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
          </details>
          {["settings", "agent-settings", "audit"].includes(section) && (
            <nav className="settings-subnav" aria-label="Settings pages">
              <Link href="/settings">General</Link>
              <Link href="/members">Members</Link>
              <Link href="/settings/agent">Agent</Link>
              <Link href="/settings/memory">Memory</Link>
              <Link href="/search">Search</Link>
              <Link href="/settings/audit">Audit log</Link>
              <Link href="/ai">Try AI</Link>
              <Link href="/inbox">Inbox</Link>
            </nav>
          )}
          {section === "new" ? (
            <CreateWorkspace user={user} />
          ) : !workspace ? (
            <NoWorkspace />
          ) : section === "channels" ? (
            <ChannelsPage
              key={workspace.id}
              workspace={workspace}
              user={user}
            />
          ) : section === "tasks" ? (
            <TasksPage key={workspace.id} workspace={workspace} user={user} />
          ) : section === "inbox" ? (
            <ApprovalsInbox key={workspace.id} workspace={workspace} />
          ) : section === "agent-settings" ? (
            <AgentSettingsPage key={workspace.id} workspace={workspace} />
          ) : section === "documents" ? (
            <DocumentsPage
              key={workspace.id}
              workspace={workspace}
              user={user}
            />
          ) : section === "search" ? (
            <SearchPage key={workspace.id} workspace={workspace} />
          ) : section === "memory" ? (
            <MemorySettingsPage key={workspace.id} workspace={workspace} />
          ) : section === "audit" ? (
            <AuditLogPage key={workspace.id} workspace={workspace} />
          ) : section === "members" ? (
            <Members key={workspace.id} workspace={workspace} user={user} />
          ) : section === "ai" ? (
            <AITrialPage key={workspace.id} workspace={workspace} />
          ) : section === "settings" ? (
            <WorkspaceSettings
              key={workspace.id}
              workspace={workspace}
              user={user}
            />
          ) : (
            <GettingStarted workspace={workspace} user={user} />
          )}
        </div>
      </main>
      {section === "home" && workspace && (
        <aside className="context-panel" aria-label="AI teammate">
          <div className="card context-card">
            <div className="row">
              <span className="agent-avatar">
                <Sparkles size={16} />
              </span>
              <div>
                <strong>Your AI teammate</strong>
                <p className="text-small text-muted">
                  Start a first conversation
                </p>
              </div>
            </div>
            <p>Start with a small question:</p>
            <ul className="prompt-ideas">
              <li>Help me break down a task</li>
              <li>Explain a piece of code</li>
              <li>Draft a short team update</li>
            </ul>
            <Button asChild variant="secondary" className="button-full">
              <Link href="/ai">
                Open Try AI <ArrowRight size={16} />
              </Link>
            </Button>
          </div>
        </aside>
      )}
      <nav className="mobile-tabs" aria-label="Main navigation">
        {[
          {
            href: "/channels",
            section: "channels",
            label: "Chat",
            Icon: MessageSquare,
          },
          {
            href: "/tasks",
            section: "tasks",
            label: "Tasks",
            Icon: LayoutGrid,
          },
          {
            href: "/channels?agent=1",
            section: "agent-panel",
            label: "Agent",
            Icon: Sparkles,
          },
          {
            href: "/settings",
            section: "settings",
            label: "Settings",
            Icon: Settings,
          },
        ].map(({ href, section: key, label, Icon }) => (
          <Link
            className="nav-item"
            key={key}
            href={href}
            aria-current={section === key ? "page" : undefined}
            onClick={(event) => {
              if (key === "agent-panel" && section === "channels") {
                event.preventDefault();
                window.dispatchEvent(new Event("tandem-agent-open"));
              }
            }}
          >
            <Icon size={20} />
            {label}
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
  const configured = useSyncExternalStore(
    subscribeSelection,
    () =>
      localStorage.getItem(`tandem-configured:${user.id}:${workspace.id}`) ===
      "true",
    () => false,
  );
  const trials = useQuery({
    queryKey: ["ai-trials", workspace.id],
    queryFn: () =>
      api<{ status: string }[]>(`/workspaces/${workspace.id}/ai/trials`),
    enabled: canManage,
  });
  const hasTeammate = (members.data?.length ?? 0) > 1;
  const steps = [
    {
      title: "Create your workspace",
      description: `${workspace.name} is ready.`,
      complete: true,
    },
    {
      title: "Invite a teammate",
      description: hasTeammate
        ? `${members.data!.length} people are working together.`
        : "Work is better with two. Add someone by email or link.",
      complete: hasTeammate,
      href: "/members",
      action: canManage ? "Invite your team" : "Meet your team",
    },
    {
      title: "Make it your own",
      description: "Give your workspace a name your whole team knows.",
      complete: configured,
      href: "/settings",
      action: "Workspace settings",
    },
    {
      title: "Ask your AI teammate",
      description: canManage
        ? "Start a conversation with a small question of your own."
        : "An Admin or Owner can start an AI conversation.",
      complete:
        trials.data?.some((trial) => trial.status === "completed") ?? false,
      href: canManage ? "/ai" : undefined,
      action: "Try AI",
    },
  ];
  const complete = steps.filter((step) => step.complete).length;
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow sr-only">{workspace.name}</div>
        <h1>
          Welcome to {workspace.name}, {user.name.split(" ")[0]}
        </h1>
        <p>Get your people and your workspace ready to work together.</p>
      </div>
      <div className="setup-progress">
        <progress
          aria-label="Workspace setup progress"
          value={complete}
          max={4}
        />
        <span>{complete} of 4</span>
      </div>
      <ErrorNotice error={members.error} />
      <div className="setup-steps">
        {steps.map((step) => (
          <section className="card setup-step" key={step.title}>
            <span
              className={`step-check ${step.complete ? "step-complete" : ""}`}
            >
              {step.complete && <Check size={18} aria-label="Complete" />}
            </span>
            <div className="setup-step-copy">
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </div>
            {step.href && (
              <Button asChild variant="secondary">
                <Link href={step.href}>{step.action}</Link>
              </Button>
            )}
          </section>
        ))}
      </div>
    </>
  );
}
function WorkspaceSettings({
  workspace,
  user,
}: {
  workspace: Workspace;
  user: User;
}) {
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
      localStorage.setItem(
        `tandem-configured:${user.id}:${workspace.id}`,
        "true",
      );
      window.dispatchEvent(new Event("tandem-workspace"));
      await client.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
  return (
    <>
      <div className="card card-body workspace-details">
        <h2>Workspace</h2>
        <p className="text-muted">Basic details your whole team sees.</p>
        <div className="workspace-logo-row">
          <span className="workspace-avatar">
            {workspace.name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{workspace.name}</strong>
            <p className="text-small text-muted">Your shared workspace</p>
          </div>
        </div>
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
          <div className="settings-actions">
            <Button
              type="reset"
              variant="secondary"
              disabled={mutation.isPending}
              onClick={() => setSaved(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canManage || mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
          {!canManage && (
            <p className="text-small text-muted" style={{ marginTop: 16 }}>
              An Admin or Owner can update workspace settings.
            </p>
          )}
        </form>
      </div>
      <div className="card card-body ownership-card">
        <h2>Ownership and access</h2>
        <p className="text-muted">
          Owners manage ownership. Admins can invite teammates and update their
          roles.
        </p>
        <Button asChild variant="secondary">
          <Link href="/members">
            Manage members <ChevronRight size={16} />
          </Link>
        </Button>
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
      <div className="card card-body permissions-card">
        <h2>What each role can do</h2>
        <p className="text-small text-muted">
          Owners manage ownership. Admins manage the team.
        </p>
        <div className="table-scroll">
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
  const [inviteOpen, setInviteOpen] = useState(false);
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
      <ErrorNotice
        error={
          members.error ?? changeRole.error ?? revoke.error ?? invite.error
        }
      />
      {canManage && (
        <ConfirmDialog
          open={inviteOpen}
          onOpenChange={(open) => {
            if (!invite.isPending) setInviteOpen(open);
          }}
          title="Invite a teammate"
          description="Create a personal link to share with your teammate. It expires in 7 days."
          actions={false}
        >
          <ErrorNotice error={invite.error} />
          <form
            className="invite-dialog-form"
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
            <div className="dialog-actions">
              <Button
                variant="secondary"
                disabled={invite.isPending}
                onClick={() => setInviteOpen(false)}
              >
                {inviteLink ? "Done" : "Cancel"}
              </Button>
              <Button type="submit" disabled={invite.isPending}>
                <UserPlus size={16} />
                {invite.isPending ? "Creating…" : "Create invitation"}
              </Button>
            </div>
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
        </ConfirmDialog>
      )}
      <div className="card members-card">
        <div className="members-card-header row-between">
          <div>
            <h2>Members</h2>
            <p className="text-small text-muted">
              {members.data?.length ?? "…"}{" "}
              {members.data?.length === 1 ? "member" : "members"} in{" "}
              {workspace.name}.
            </p>
          </div>
          {canManage && (
            <Button
              onClick={() => {
                invite.reset();
                setInviteLink("");
                setCopyError(null);
                setInviteOpen(true);
              }}
            >
              <Plus size={16} />
              Invite
            </Button>
          )}
        </div>
        <div className="table-scroll">
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
                    <span
                      className={`avatar avatar-color-${(members.data!.indexOf(member) % 3) + 1}`}
                    >
                      {member.name.slice(0, 1).toUpperCase()}
                    </span>
                    <div>
                      <div className="member-name">
                        {member.name}
                        {member.user_id === user.id ? " (you)" : ""}
                      </div>
                      <div className="text-small text-muted">
                        {member.email}
                      </div>
                    </div>
                  </div>
                  <div role="cell">
                    {canEdit ? (
                      <>
                        <Label
                          htmlFor={`role-${member.id}`}
                          className="sr-only"
                        >
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
                      <span className="text-small text-muted member-protection">
                        {protectedOwner && ownerCount <= 1 ? "Last Owner" : "—"}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {canManage && (
        <>
          <div className="card card-body pending-card">
            <h2>Pending invitations</h2>
            <p className="text-small text-muted">
              Only the invited email address can use each link.
            </p>
            <ErrorNotice error={invitations.error} />
            {invitations.isPending ? (
              <p role="status">Loading invitations…</p>
            ) : !invitations.data?.some(
                (item) =>
                  item.status === "pending" || item.status === "expired",
              ) ? (
              <p className="text-muted" style={{ margin: 0 }}>
                No pending invitations. Your next teammate could be one link
                away.
              </p>
            ) : (
              invitations.data
                ?.filter(
                  (item) =>
                    item.status === "pending" || item.status === "expired",
                )
                .map((item) => (
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
                      <Button
                        variant="secondary"
                        disabled={invite.isPending || revoke.isPending}
                        onClick={() => {
                          const form = new FormData();
                          form.set("email", item.email);
                          form.set("role", item.role);
                          invite.mutate(form, {
                            onSuccess: () => setInviteOpen(true),
                          });
                        }}
                      >
                        Renew link
                      </Button>
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
