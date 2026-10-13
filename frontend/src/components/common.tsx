"use client";
import Link from "next/link";
import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function Logo() {
  return (
    <Link href="/" className="logo" aria-label="Tandem home">
      <span className="logo-mark" aria-hidden="true">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <circle cx="9" cy="12" r="5" stroke="currentColor" strokeWidth="2" />
          <circle
            cx="15"
            cy="12"
            r="5"
            stroke="currentColor"
            strokeWidth="2"
            opacity=".7"
          />
        </svg>
      </span>
      <span className="wordmark">Tandem</span>
    </Link>
  );
}
export function ErrorNotice({ error }: { error: unknown }) {
  return error ? (
    <div role="alert" className="error">
      {error instanceof Error
        ? error.message
        : "Something went wrong. Please try again."}
    </div>
  ) : null;
}
export function Field({
  label,
  id,
  help,
  labelAction,
  ...props
}: React.ComponentProps<typeof Input> & {
  label: string;
  id: string;
  help?: string;
  labelAction?: React.ReactNode;
}) {
  return (
    <div className="field">
      <div className="field-label-row">
        <Label htmlFor={id}>{label}</Label>
        {labelAction}
      </div>
      <Input
        id={id}
        aria-describedby={help ? `${id}-help` : undefined}
        {...props}
      />
      {help && (
        <span id={`${id}-help`} className="text-small text-muted">
          {help}
        </span>
      )}
    </div>
  );
}
function subscribeTheme(callback: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener("tandem-theme", callback);
  window.addEventListener("storage", callback);
  media.addEventListener("change", callback);
  return () => {
    window.removeEventListener("tandem-theme", callback);
    window.removeEventListener("storage", callback);
    media.removeEventListener("change", callback);
  };
}
function themeSnapshot() {
  const theme = localStorage.getItem("tandem-theme");
  return (
    theme === "dark" ||
    (!theme && window.matchMedia("(prefers-color-scheme: dark)").matches)
  );
}
export function ThemeToggle() {
  const dark = useSyncExternalStore(subscribeTheme, themeSnapshot, () => false);
  function toggle() {
    localStorage.setItem("tandem-theme", dark ? "light" : "dark");
    document.documentElement.classList.toggle("dark", !dark);
    window.dispatchEvent(new Event("tandem-theme"));
  }
  return (
    <Button
      variant="ghost"
      onClick={toggle}
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
    >
      {dark ? <Moon size={18} /> : <Sun size={18} />}
      <span className="theme-label">{dark ? "Dark" : "Light"}</span>
    </Button>
  );
}
