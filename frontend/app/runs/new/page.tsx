"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { createTask } from "@/lib/api";
import { saveTaskSnapshot } from "@/lib/supabase";

export default function NewRunPage() {
  const router = useRouter();
  const { user, token, capabilities } = useAuth();
  const [url, setUrl] = useState("https://example.com");
  const [instruction, setInstruction] = useState(
    "Summarise this page and list the main links.",
  );
  const [useAi, setUseAi] = useState(true);
  const [screenshot, setScreenshot] = useState(false);
  const [maxLinks, setMaxLinks] = useState(25);
  const [timeoutMs, setTimeoutMs] = useState(30000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const task = await createTask(
        {
          url,
          instruction,
          ai: useAi,
          include_screenshot: screenshot,
          max_links: maxLinks,
          timeout_ms: timeoutMs,
        },
        token,
      );
      if (user) await saveTaskSnapshot(task).catch(() => undefined);
      router.push(`/runs/${task.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not queue the run.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Launch a new run</h1>
        <p className="mt-2 text-sm text-nex-muted">
          Queue an autonomous browser task. Track status, logs, and results from the task detail page.
        </p>
      </div>

      {capabilities?.auth.required && !user ? (
        <div className="rounded-xl border border-amber-400/40 bg-amber-400/10 p-4 text-sm text-amber-100">
          This backend requires Supabase authentication. Sign in from Settings before queuing a run.
        </div>
      ) : null}

      <form className="nex-card space-y-5 p-6" onSubmit={handleSubmit}>
        <div>
          <label className="nex-label" htmlFor="url">Target URL</label>
          <input
            id="url"
            className="nex-input"
            type="url"
            required
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com"
          />
          <p className="mt-2 text-xs text-nex-muted">
            Only public http(s) URLs on ports 80/443 are accepted. Private and metadata addresses are blocked.
          </p>
        </div>

        <div>
          <label className="nex-label" htmlFor="instruction">Instruction</label>
          <textarea
            id="instruction"
            className="nex-input min-h-32 resize-y"
            required
            maxLength={2000}
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="nex-label" htmlFor="maxLinks">Maximum links</label>
            <input
              id="maxLinks"
              className="nex-input"
              type="number"
              min={0}
              max={200}
              value={maxLinks}
              onChange={(event) => setMaxLinks(Number(event.target.value))}
            />
          </div>
          <div>
            <label className="nex-label" htmlFor="timeout">Timeout (ms)</label>
            <input
              id="timeout"
              className="nex-input"
              type="number"
              min={1000}
              max={120000}
              step={1000}
              value={timeoutMs}
              onChange={(event) => setTimeoutMs(Number(event.target.value))}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={useAi}
              onChange={(event) => setUseAi(event.target.checked)}
            />
            Use AI planner {capabilities?.ai.configured ? "" : "(not configured)"}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={screenshot}
              onChange={(event) => setScreenshot(event.target.checked)}
            />
            Capture full-page screenshot
          </label>
        </div>

        {error ? <p className="text-sm text-nex-danger">{error}</p> : null}

        <div className="flex flex-wrap items-center gap-3">
          <button className="nex-btn nex-btn-primary" type="submit" disabled={busy}>
            {busy ? "Queuing…" : "Queue task"}
          </button>
          <span className="text-xs text-nex-muted">
            The task worker can be cancelled at any time.
          </span>
        </div>
      </form>
    </div>
  );
}
