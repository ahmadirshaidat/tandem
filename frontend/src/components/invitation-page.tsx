"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Users } from "lucide-react";
import { ErrorNotice, Logo, ThemeToggle } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  api,
  roleLabels,
  type InvitePreview,
  type User,
  type Workspace,
} from "@/lib/api";
export function InvitationPage() {
  const params = useSearchParams();
  const token = params.get("token");
  const router = useRouter();
  const client = useQueryClient();
  const invitation = useQuery({
    queryKey: ["invite", token],
    queryFn: () =>
      api<InvitePreview>(`/invitations/${encodeURIComponent(token!)}`),
    enabled: !!token,
    retry: false,
  });
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    retry: false,
  });
  const accept = useMutation({
    mutationFn: () =>
      api<Workspace>(`/invitations/${encodeURIComponent(token!)}/accept`, {
        method: "POST",
      }),
    onSuccess: async (workspace) => {
      localStorage.setItem(`tandem-workspace:${me.data!.id}`, workspace.id);
      await client.invalidateQueries({ queryKey: ["workspaces"] });
      router.replace("/");
    },
  });
  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      client.clear();
      router.replace(
        `/login?next=${encodeURIComponent(`/accept-invitation?token=${token}`)}&email=${encodeURIComponent(invitation.data?.email ?? "")}`,
      );
    },
  });
  const next = `/accept-invitation?token=${token ?? ""}`;
  return (
    <div className="invitation-layout">
      <main className="invitation-panel">
        <header className="invitation-top row-between">
          <Logo />
          <ThemeToggle />
        </header>
        <div className="card invitation-card">
          <span className="invitation-symbol">
            <Users size={24} />
          </span>
          <h1>
            {invitation.data
              ? `You’re invited to join ${invitation.data.workspace_name}`
              : "You’re invited."}
          </h1>
          {!token ? (
            <div className="error" role="alert">
              Open the invitation link your teammate shared with you.
            </div>
          ) : invitation.isPending ? (
            <p role="status">Opening your invitation…</p>
          ) : invitation.error ? (
            <>
              <ErrorNotice error={invitation.error} />
              <p className="text-muted">
                Ask an Admin or Owner for a new invitation.
              </p>
              <Button asChild variant="secondary">
                <Link href="/">Back to your workspace</Link>
              </Button>
            </>
          ) : (
            invitation.data && (
              <>
                <p className="text-muted">
                  You will join as an{" "}
                  <strong>{roleLabels[invitation.data.role]}</strong>.
                </p>
                <span className="chip chip-brand">
                  {roleLabels[invitation.data.role]}
                </span>
                <p className="text-small text-muted">
                  This invitation is for {invitation.data.email}.
                </p>
                <ErrorNotice error={accept.error ?? logout.error} />
                {me.isPending ? (
                  <p role="status">Checking your account…</p>
                ) : me.data ? (
                  me.data.email === invitation.data.email ? (
                    <Button
                      className="button-full"
                      disabled={accept.isPending}
                      onClick={() => accept.mutate()}
                    >
                      {accept.isPending ? "Joining…" : "Accept invitation"}
                      <ArrowRight size={16} />
                    </Button>
                  ) : (
                    <>
                      <p className="text-muted">
                        You’re signed in as {me.data.email}. Switch to the
                        invited account to join.
                      </p>
                      <Button
                        className="button-full"
                        onClick={() => logout.mutate()}
                        disabled={logout.isPending}
                      >
                        Switch account
                      </Button>
                    </>
                  )
                ) : (
                  <div className="stack">
                    <Button asChild className="button-full">
                      <Link
                        href={`/signup?next=${encodeURIComponent(next)}&email=${encodeURIComponent(invitation.data.email)}`}
                      >
                        Create an account and join <ArrowRight size={16} />
                      </Link>
                    </Button>
                    <Button asChild variant="secondary" className="button-full">
                      <Link
                        href={`/login?next=${encodeURIComponent(next)}&email=${encodeURIComponent(invitation.data.email)}`}
                      >
                        I already have an account
                      </Link>
                    </Button>
                  </div>
                )}
              </>
            )
          )}
        </div>
      </main>
    </div>
  );
}
