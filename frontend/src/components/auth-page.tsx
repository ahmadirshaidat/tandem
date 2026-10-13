"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Users, ShieldCheck } from "lucide-react";
import { ErrorNotice, Field, Logo, ThemeToggle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { api, post, type User } from "@/lib/api";
import { safeNext } from "@/lib/utils";

type AuthMode = "login" | "signup" | "forgot-password" | "reset-password";
const copy = {
  login: {
    eyebrow: "WELCOME BACK",
    title: "Good to see you again.",
    description: "Log in and pick up where your team left off.",
    button: "Log in",
  },
  signup: {
    eyebrow: "A NEW WAY TO WORK TOGETHER",
    title: "Make room for your team.",
    description: "Create your account. Your shared workspace is next.",
    button: "Create account",
  },
  "forgot-password": {
    eyebrow: "LET’S GET YOU BACK IN",
    title: "Forgot your password?",
    description: "Enter your email and we’ll send a link to reset it.",
    button: "Send reset link",
  },
  "reset-password": {
    eyebrow: "A FRESH START",
    title: "Choose a new password.",
    description: "Use at least 10 characters to keep your account safe.",
    button: "Update password",
  },
};
export function AuthPage({ mode }: { mode: AuthMode }) {
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const next = safeNext(params.get("next"));
  const item = copy[mode];
  const action = useMutation({
    mutationFn: async (form: FormData) => {
      const email = String(form.get("email") ?? "");
      const password = String(form.get("password") ?? "");
      if (mode === "forgot-password")
        return api<{ message: string }>(
          "/auth/forgot-password",
          post({ email }),
        );
      if (mode === "reset-password")
        return api<{ message: string }>(
          "/auth/reset-password",
          post({ token: params.get("token"), password }),
        );
      return api<User>(
        mode === "signup" ? "/auth/register" : "/auth/login",
        post({
          email,
          password,
          ...(mode === "signup" ? { name: form.get("name") } : {}),
        }),
      );
    },
    onSuccess: (data) => {
      if (mode === "login" || mode === "signup") {
        client.clear();
        client.setQueryData(["me"], data);
        router.replace(next);
      }
    },
  });
  const authSuccess =
    action.isSuccess &&
    (mode === "forgot-password" || mode === "reset-password");
  const switchLink = `${mode === "login" ? "/signup" : "/login"}?next=${encodeURIComponent(next)}${params.get("email") ? `&email=${encodeURIComponent(params.get("email")!)}` : ""}`;
  return (
    <div className="auth-layout">
      <aside className="auth-story">
        <Logo />
        <div className="auth-story-content">
          <span className="chip chip-agent">
            <Users size={14} /> Better, together
          </span>
          <h2>
            A shared place
            <br />
            to build what’s next.
          </h2>
          <p>
            Less scattered work. More shared understanding. Give your team a
            place to move forward together.
          </p>
          <div className="card story-card">
            <div className="card-body">
              <div className="eyebrow">YOUR TEAM, IN TANDEM</div>
              {[
                "One workspace for your people",
                "Clear roles, shared ownership",
                "A calm place to get started",
              ].map((text) => (
                <div className="row check-row" key={text}>
                  <Check className="check-icon" size={18} />
                  {text}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="row text-small text-muted">
          <ShieldCheck size={16} /> Your team’s work stays with your team.
        </div>
      </aside>
      <main className="auth-main">
        <header className="auth-top">
          <span className="mobile-brand">
            <Logo />
          </span>
          <ThemeToggle />
        </header>
        <div className="auth-form">
          <div className="eyebrow">{item.eyebrow}</div>
          <h1>{item.title}</h1>
          <p className="text-muted">{item.description}</p>
          <ErrorNotice error={action.error} />
          {authSuccess ? (
            <div>
              <div role="status" className="notice">
                {"message" in action.data ? action.data.message : "Done."}
              </div>
              <Button asChild className="button-full">
                <Link href="/login">
                  Back to log in <ArrowRight size={16} />
                </Link>
              </Button>
            </div>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                action.mutate(new FormData(event.currentTarget));
              }}
            >
              {mode === "signup" && (
                <Field
                  label="Your name"
                  id="name"
                  name="name"
                  autoComplete="name"
                  required
                  maxLength={80}
                  placeholder="Alex Morgan"
                />
              )}
              {mode !== "reset-password" && (
                <Field
                  label="Email address"
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  maxLength={254}
                  defaultValue={params.get("email") ?? ""}
                  placeholder="you@yourteam.com"
                />
              )}
              {mode !== "forgot-password" && (
                <Field
                  label={
                    mode === "reset-password" ? "New password" : "Password"
                  }
                  id="password"
                  name="password"
                  type="password"
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  required
                  minLength={mode === "login" ? 1 : 10}
                  maxLength={128}
                  help={
                    mode === "signup" ? "At least 10 characters." : undefined
                  }
                />
              )}
              {mode === "login" && (
                <p className="text-small" style={{ textAlign: "right" }}>
                  <Link href="/forgot-password">Forgot password?</Link>
                </p>
              )}
              <Button
                type="submit"
                className="button-full"
                disabled={
                  action.isPending ||
                  (mode === "reset-password" && !params.get("token"))
                }
              >
                {action.isPending ? "Please wait…" : item.button}
                <ArrowRight size={16} />
              </Button>
              {mode === "reset-password" && !params.get("token") && (
                <p role="alert" className="error">
                  Open the password reset link from your email.
                </p>
              )}
            </form>
          )}
          {(mode === "login" || mode === "signup") && (
            <p className="auth-bottom">
              {mode === "login" ? "New to Tandem?" : "Already have an account?"}{" "}
              <Link href={switchLink}>
                {mode === "login" ? "Create an account" : "Log in"}
              </Link>
            </p>
          )}
          {mode === "forgot-password" && !authSuccess && (
            <p className="auth-bottom">
              <Link href="/login">Back to log in</Link>
            </p>
          )}
        </div>
        <footer className="auth-bottom">
          A little less friction. A lot more together.
        </footer>
      </main>
    </div>
  );
}
