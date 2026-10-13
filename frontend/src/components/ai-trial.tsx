"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Check,
  FlaskConical,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { ErrorNotice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, post, type Workspace } from "@/lib/api";

type ProviderId = "groq" | "gemini" | "deepseek" | "openai";
type ProviderInfo = { id: ProviderId; configured: boolean; model: string };
type ProviderStatus = {
  primary: ProviderId;
  providers: ProviderInfo[];
  max_prompt_characters: number;
  max_output_tokens: number;
  requests_per_minute: number;
};
type Attempt = {
  provider: ProviderId;
  status: string;
  category?: string;
  http_status?: number;
  elapsed_ms?: number;
};
type Answer = {
  id: string;
  provider: ProviderId;
  model: string;
  answer: string;
  attempts: Attempt[];
  input_tokens: number | null;
  output_tokens: number | null;
};
type Trial = {
  id: string;
  status: string;
  provider: ProviderId | null;
  attempts: Attempt[];
  created_at: string;
};
const names: Record<ProviderId, string> = {
  groq: "Groq",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  openai: "OpenAI",
};
const categories: Record<string, string> = {
  not_configured: "No key configured",
  authentication_or_access: "Key or access rejected",
  rate_limited: "Provider rate limit",
  billing_required: "Provider balance required",
  invalid_request: "Model or request rejected",
  unavailable: "Provider unavailable",
  empty_response: "No answer returned",
};

export function AITrialPage({ workspace }: { workspace: Workspace }) {
  const allowed = ["owner", "admin"].includes(workspace.role);
  const client = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [provider, setProvider] = useState("auto");
  const status = useQuery({
    queryKey: ["ai-providers", workspace.id],
    queryFn: () =>
      api<ProviderStatus>(`/workspaces/${workspace.id}/ai/providers`),
    enabled: allowed,
  });
  const history = useQuery({
    queryKey: ["ai-trials", workspace.id],
    queryFn: () => api<Trial[]>(`/workspaces/${workspace.id}/ai/trials`),
    enabled: allowed,
  });
  const trial = useMutation({
    mutationFn: () =>
      api<Answer>(
        `/workspaces/${workspace.id}/ai/trials`,
        post({ prompt, provider }),
      ),
    onSettled: () =>
      client.invalidateQueries({ queryKey: ["ai-trials", workspace.id] }),
  });
  if (!allowed)
    return (
      <div className="empty">
        <span className="icon-circle">
          <ShieldCheck />
        </span>
        <h1>An Admin or Owner can run trials.</h1>
        <p>
          Your workspace permissions keep provider trials with the people who
          manage the team.
        </p>
      </div>
    );
  const configured =
    status.data?.providers.filter((item) => item.configured) ?? [];
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">{workspace.name} / AI TRIAL</div>
        <h1>A first conversation.</h1>
        <p>Try your AI teammate with a small question.</p>
      </div>
      <ErrorNotice error={status.error} />
      <div className="ai-provider-grid">
        {status.isPending ? (
          <p role="status">Checking provider settings…</p>
        ) : (
          status.data?.providers.map((item) => (
            <div className="card card-body" key={item.id}>
              <div className="row-between">
                <h3 style={{ margin: 0 }}>{names[item.id]}</h3>
                <span className={`chip ${item.configured ? "chip-agent" : ""}`}>
                  {item.configured ? (
                    <>
                      <Check size={12} />
                      Key configured
                    </>
                  ) : (
                    "Not configured"
                  )}
                </span>
              </div>
              <p
                className="text-small text-muted"
                style={{ margin: "16px 0 0" }}
              >
                {item.model}
              </p>
            </div>
          ))
        )}
      </div>
      <div className="notice" style={{ marginTop: 24 }}>
        Use test data. The provider receives only the question you send;
        workspace history is not included. A configured key still needs a
        successful provider response.
      </div>
      <div className="card card-body">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            trial.mutate();
          }}
        >
          <div className="field">
            <Label htmlFor="ai-provider">Provider</Label>
            <select
              className="input"
              id="ai-provider"
              value={provider}
              onChange={(event) => {
                setProvider(event.target.value);
                trial.reset();
              }}
              disabled={trial.isPending}
            >
              <option value="auto">
                Automatic ·{" "}
                {status.data ? names[status.data.primary] : "primary"} first
              </option>
              {status.data?.providers.map((item) => (
                <option
                  value={item.id}
                  key={item.id}
                  disabled={!item.configured}
                >
                  {names[item.id]}
                  {!item.configured ? " · not configured" : ""}
                </option>
              ))}
            </select>
            <span className="text-small text-muted">
              Automatic mode tries configured alternatives if a provider is
              unavailable.
            </span>
          </div>
          <div className="field">
            <Label htmlFor="ai-prompt">Your test question</Label>
            <textarea
              id="ai-prompt"
              className="input ai-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              required
              minLength={1}
              maxLength={4000}
              rows={5}
              placeholder="Suggest three ways to make a bug report clearer."
              disabled={trial.isPending}
              aria-describedby="ai-limits"
            />
            <span id="ai-limits" className="text-small text-muted">
              {prompt.length} / 4,000 characters · Up to{" "}
              {status.data?.max_output_tokens ?? 512} output tokens ·{" "}
              {status.data?.requests_per_minute ?? 5} requests per minute
            </span>
          </div>
          <ErrorNotice error={trial.error} />
          <Button
            type="submit"
            disabled={trial.isPending || !prompt.trim() || !configured.length}
          >
            <Sparkles size={16} />
            {trial.isPending ? "Asking your teammate…" : "Send test question"}
            <ArrowUpRight size={16} />
          </Button>
          {trial.isPending && (
            <p
              role="status"
              className="text-small text-muted"
              style={{ marginTop: 16 }}
            >
              Waiting for the provider. Automatic mode may try an alternative.
            </p>
          )}
        </form>
      </div>
      {trial.data && (
        <div className="card ai-answer" role="status">
          <div className="card-body">
            <div className="row-between">
              <div className="row">
                <span className="icon-circle">
                  <Sparkles size={20} />
                </span>
                <div>
                  <h2 style={{ margin: 0 }}>Your teammate’s reply</h2>
                  <span className="text-small text-muted">
                    {names[trial.data.provider]} · {trial.data.model}
                  </span>
                </div>
              </div>
            </div>
            <p className="ai-answer-text">{trial.data.answer}</p>
            <div className="row text-small text-muted">
              <FlaskConical size={16} />
              {trial.data.attempts.filter((item) => item.status === "failed")
                .length
                ? "An alternative provider answered."
                : "Provider answered directly."}
            </div>
          </div>
        </div>
      )}
      <div className="section-heading">
        <h2>Recent trials</h2>
        <p className="text-muted">
          Provider attempts are recorded. Questions and answers are not saved in
          this history.
        </p>
      </div>
      <ErrorNotice error={history.error} />
      <div className="card card-body">
        {history.isPending ? (
          <p role="status">Loading trials…</p>
        ) : !history.data?.length ? (
          <p className="text-muted" style={{ margin: 0 }}>
            No trials yet. Start with a small question above.
          </p>
        ) : (
          history.data.map((item) => (
            <div className="ai-history-item" key={item.id}>
              <div className="row-between">
                <span
                  className={`chip ${item.status === "completed" ? "chip-success" : "chip-warning"}`}
                >
                  {item.status === "completed" ? "Answered" : "No answer"}
                </span>
                <time
                  className="text-small text-muted"
                  dateTime={item.created_at}
                >
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </div>
              <div className="ai-attempts">
                {item.attempts.map((attempt, index) => (
                  <span className="chip" key={index}>
                    {names[attempt.provider]} ·{" "}
                    {attempt.status === "completed"
                      ? "Answered"
                      : (categories[attempt.category ?? ""] ?? attempt.status)}
                  </span>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
