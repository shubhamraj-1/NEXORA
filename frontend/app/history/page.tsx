"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { RunHistoryExports } from "@/components/ExportButtons";
import { ResultView } from "@/components/ResultView";
import {
  deleteRun,
  isSupabaseConfigured,
  listRuns,
  type SavedRun,
} from "@/lib/supabase";

export default function HistoryPage() {
  const { user } = useAuth();
  const [runs, setRuns] = useState<SavedRun[]>([]);
  const [opened, setOpened] = useState<SavedRun | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) {
      setRuns([]);
      return;
    }
    setBusy(true);
    try {
      setRuns(await listRuns());
      setMessage(null);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not load history.");
    } finally {
      setBusy(false);
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete(id: string) {
    try {
      await deleteRun(id);
      if (opened?.id === id) setOpened(null);
      await load();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not delete run.");
    }
  }

  if (!isSupabaseConfigured() || !user) {
    return (
      <div className="nex-card p-12 text-center">
        <h1 className="text-xl font-semibold">Saved results</h1>
        <p className="mx-auto mt-3 max-w-md text-sm text-nex-muted">
          Sign in with Supabase to view private run history stored in PostgreSQL.
        </p>
        <Link href="/settings" className="nex-btn nex-btn-primary mt-6">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Saved results</h1>
          <p className="mt-2 text-sm text-nex-muted">
            Private runs synced to your Supabase account.
          </p>
        </div>
        <RunHistoryExports runs={runs} />
      </div>

      {message ? <p className="text-sm text-nex-danger">{message}</p> : null}

      {runs.length === 0 ? (
        <div className="nex-card p-12 text-center">
          <p className="text-sm text-nex-muted">
            {busy ? "Loading…" : "No saved runs yet."}
          </p>
          <Link href="/runs/new" className="mt-3 inline-block text-sm text-nex-accent">
            Run the agent
          </Link>
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {runs.map((run) => (
            <div key={run.id} className="nex-card flex flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold">
                    {run.title || "(untitled)"}
                  </h2>
                  <p className="mt-1 truncate text-xs text-nex-muted">{run.url}</p>
                </div>
                <span className="nex-pill">{run.status_code ?? "—"}</span>
              </div>
              <p className="mt-3 line-clamp-2 text-xs text-white/70">
                {run.instruction}
              </p>
              {run.answer ? (
                <p className="mt-3 line-clamp-3 text-xs text-nex-muted">{run.answer}</p>
              ) : null}
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4">
                <span className="text-xs text-nex-muted">
                  {new Date(run.created_at).toLocaleString()}
                </span>
                <div className="flex gap-2">
                  <button
                    className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
                    onClick={() => setOpened(run)}
                  >
                    Open
                  </button>
                  <button
                    className="nex-btn nex-btn-danger !px-3 !py-2 text-xs"
                    onClick={() => void handleDelete(run.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {opened ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Opened run</h2>
            <button
              className="text-xs text-nex-muted hover:text-white"
              onClick={() => setOpened(null)}
            >
              Close
            </button>
          </div>
          <ResultView result={opened.result ?? {}} title={opened.title || "Saved run"} />
        </div>
      ) : null}
    </div>
  );
}
