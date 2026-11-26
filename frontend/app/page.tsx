"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { listTasks, type TaskRecord } from "@/lib/api";
import { listSavedTasks, type SavedTask } from "@/lib/supabase";

export default function OverviewPage() {
  const { user, token, capabilities, supabaseReady } = useAuth();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [saved, setSaved] = useState<SavedTask[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const authRequired = capabilities?.auth.required ?? false;
  const signedOut = authRequired && !token;
  const canLoad = Boolean(capabilities) && (!authRequired || Boolean(token));

  const load = useCallback(async () => {
    setMessage(null);
    if (!canLoad) {
      setTasks([]);
      setSaved([]);
      return;
    }
    try {
      setTasks(await listTasks(token));
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not load tasks.");
    }
    if (user && supabaseReady) {
      try {
        setSaved(await listSavedTasks());
      } catch {
        // Saved Supabase tasks are optional; backend tasks remain authoritative.
      }
    } else {
      setSaved([]);
    }
  }, [token, user, supabaseReady, canLoad]);

  useEffect(() => {
    void load();
  }, [load]);

  const succeeded = tasks.filter((task) => task.status === "succeeded").length;
  const active = tasks.filter(
    (task) => task.status === "queued" || task.status === "running",
  ).length;
  const failed = tasks.filter((task) => task.status === "failed").length;

  return (
    <div className="space-y-8">
      <section className="nex-card relative overflow-hidden p-8">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-nex-accent/20 blur-3xl" />
        <div className="relative">
          <div className="nex-pill mb-5">
            <span className="nex-dot" />
            Browser task runner
          </div>
          <h1 className="max-w-2xl text-3xl font-bold leading-tight md:text-5xl">
            Run browser tasks, inspect the results.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-nex-muted md:text-base">
            NEXORA drives Chromium, extracts structured page data, traces each
            step, and optionally uses OpenAI for planning and answers.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/runs/new" className="nex-btn nex-btn-primary">
              Launch a new run →
            </Link>
            <Link href="/runs" className="nex-btn nex-btn-ghost">
              View task queue
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total tasks" value={tasks.length} hint="This session" />
        <StatCard label="Active" value={active} hint="Queued + running" />
        <StatCard label="Succeeded" value={succeeded} hint="Results available" />
        <StatCard label="Failed" value={failed} hint="Retry from task detail" />
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="nex-card p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent tasks</h2>
            <Link href="/runs" className="text-xs text-nex-accent hover:underline">
              See all
            </Link>
          </div>
          {message ? <p className="text-sm text-nex-danger">{message}</p> : null}
          {tasks.length === 0 ? (
            <div className="rounded-xl border border-dashed border-nex-line p-8 text-center">
              <p className="text-sm text-nex-muted">
                {signedOut ? "Sign in to see your tasks." : "No tasks yet."}
              </p>
              <Link
                href={signedOut ? "/settings" : "/runs/new"}
                className="mt-3 inline-block text-sm text-nex-accent"
              >
                {signedOut ? "Sign in" : "Create your first run"}
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {tasks.slice(0, 6).map((task) => (
                <Link
                  key={task.id}
                  href={`/runs/${task.id}`}
                  className="flex items-center justify-between gap-4 rounded-xl border border-nex-line bg-black/20 p-3 transition hover:border-nex-accent/50"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{task.request.url}</div>
                    <div className="truncate text-xs text-nex-muted">
                      {task.request.instruction}
                    </div>
                  </div>
                  <StatusBadge status={task.status} />
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="nex-card p-5">
            <h2 className="mb-4 text-lg font-semibold">System status</h2>
            <StatusRow label="Browser engine" value={capabilities?.browser.engine ?? "checking"} ok />
            <StatusRow
              label="AI planner"
              value={capabilities?.ai.configured ? capabilities.ai.model ?? "on" : "optional"}
              ok={capabilities?.ai.configured ?? false}
            />
            <StatusRow
              label="Supabase history"
              value={supabaseReady ? (user ? "signed in" : "ready") : "not configured"}
              ok={supabaseReady && Boolean(user)}
            />
            <StatusRow
              label="Rate limit"
              value={`${capabilities?.limits.rate_limit_per_minute ?? "—"}/min`}
              ok
            />
          </div>
          <div className="nex-card p-5">
            <h2 className="mb-2 text-sm font-semibold">Supabase sync</h2>
            <p className="text-xs leading-6 text-nex-muted">
              {user
                ? `${saved.length} task snapshots synced for ${user.email ?? "this account"}.`
                : "Sign in to sync task snapshots, logs, and results to Supabase."}
            </p>
            <Link href="/settings" className="mt-3 inline-block text-xs text-nex-accent">
              Configure account →
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint: string;
}) {
  return (
    <div className="nex-card p-5">
      <div className="text-[11px] uppercase tracking-widest text-nex-muted">{label}</div>
      <div className="mt-2 text-3xl font-bold">{value}</div>
      <div className="mt-1 text-xs text-nex-muted">{hint}</div>
    </div>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-nex-line/60 py-2 last:border-0">
      <span className="text-xs text-nex-muted">{label}</span>
      <span className="flex items-center gap-2 text-xs font-medium">
        <span className={ok ? "nex-dot" : "nex-dot nex-dot-off"} />
        {value}
      </span>
    </div>
  );
}
