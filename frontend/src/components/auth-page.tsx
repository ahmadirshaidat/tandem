"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Github,
  MessageSquare,
  Users,
  ShieldCheck,
} from "lucide-react";
import { ErrorNotice, Field, Logo, ThemeToggle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { api, post, type User } from "@/lib/api";
import { safeNext } from "@/lib/utils";
import { ProposalPreview } from "@/components/design-preview";

type AuthMode = "login" | "signup" | "forgot-password" | "reset-password";
const copy = {
  login: {
    eyebrow: "WELCOME BACK",
    title: "Welcome back",
    description: "Log in to your workspace.",
    button: "Log in",
  },
  signup: {
    eyebrow: "A NEW WAY TO WORK TOGETHER",
    title: "Create your account",
    description: "Your team’s shared workspace starts here.",
    button: "Create account",
  },
  "forgot-password": {
    eyebrow: "LET’S GET YOU BACK IN",
    title: "Reset your password",
    description:
      "Enter your email and we will send you a link to choose a new password.",
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
      <main className="auth-main">
        <header className="auth-top row-between">
          <Logo />
          <ThemeToggle />
        </header>
        <div className="auth-form">
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
            <>
              {(mode === "login" || mode === "signup") && (
                <div className="auth-providers">
                  <Button
                    variant="secondary"
                    className="button-full auth-provider"
                    disabled
                    aria-describedby="provider-note"
                  >
                    <span className="google-mark" aria-hidden="true">
                      G
                    </span>
                    Continue with Google
                  </Button>
                  <Button
                    variant="secondary"
                    className="button-full auth-provider"
                    disabled
                    aria-describedby="provider-note"
                  >
                    <Github size={18} />
                    Continue with GitHub
                  </Button>
                  <p id="provider-note" className="text-small text-muted">
                    Google and GitHub sign-in are not available yet.
                  </p>
                  <div className="auth-divider">
                    <span>or use email</span>
                  </div>
                </div>
              )}
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  action.mutate(new FormData(event.currentTarget));
                }}
              >
                {mode === "signup" && (
                  <Field
                    label="Full name"
                    aria-label="Your name"
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
                    label={mode === "signup" ? "Work email" : "Email"}
                    aria-label="Email address"
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
                    placeholder={
                      mode === "login"
                        ? "Your password"
                        : "At least 10 characters"
                    }
                    labelAction={
                      mode === "login" ? (
                        <Link href="/forgot-password">Forgot password?</Link>
                      ) : undefined
                    }
                  />
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
                </Button>
                {mode === "reset-password" && !params.get("token") && (
                  <p role="alert" className="error">
                    Open the password reset link from your email.
                  </p>
                )}
              </form>
            </>
          )}
          {(mode === "login" || mode === "signup") && (
            <p className="auth-bottom">
              {mode === "login" ? "New here?" : "Already have an account?"}{" "}
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
      </main>
      <aside className="auth-story" aria-label="About Tandem">
        <div className="auth-story-content">
          {mode === "signup" ? (
            <>
              <h2>Set up your team in about two minutes.</h2>
              <div className="signup-features">
                {[
                  {
                    Icon: Users,
                    title: "One shared workspace",
                    text: "Bring your people together and keep everyone in the loop.",
                  },
                  {
                    Icon: ShieldCheck,
                    title: "A role for every teammate",
                    text: "Give each person the access they need, with clear ownership.",
                  },
                  {
                    Icon: MessageSquare,
                    title: "Start a conversation with AI",
                    text: "Try your AI teammate with a question of your own.",
                  },
                ].map(({ Icon, title, text }) => (
                  <div className="signup-feature" key={title}>
                    <span className="signup-feature-icon">
                      <Icon size={20} />
                    </span>
                    <div>
                      <h3>{title}</h3>
                      <p>{text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <>
              <h2>Pick up where your team left off.</h2>
              <ProposalPreview />
              <p>
                A shared place for your people, their work, and your AI
                teammate.
              </p>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
