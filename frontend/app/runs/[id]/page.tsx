"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ResultView } from "@/components/ResultView";
import { StatusBadge } from "@/components/StatusBadge";
import {
  cancelTask,
  getTask,
  type AgentRunResponse,
  type TaskLog,
  type TaskRecord,
} from "@/lib/api";
import { downloadJson } from "@/lib/exports";
import {
  getSavedTaskResult,
  listSavedTasks,
  listTaskLogs,
  saveTaskLogs,
  saveTaskResult,
  saveTaskSnapshot,
} from "@/lib/supabase";

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const taskId = params.id;
  const { user, token } = useAuth();
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [result, setResult] = useState<AgentRunResponse | Partial<AgentRunResponse> | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const syncedKey = useRef("");

  const load = useCallback(async () => {
    try {
      const current = await getTask(taskId, token);
      setTask(current);
      setLogs(current.logs);
      setResult(current.result);
      setMessage(null);

      if (user) {
        const key = `${current.id}:${current.status}:${current.updated_at}`;
        if (syncedKey.current !== key) {
          syncedKey.current = key;
          await saveTaskSnapshot(current).catch(() => undefined);
          await saveTaskLogs(current.id, current.logs).catch(() => undefined);
          if (current.result) {
            await saveTaskResult(current.id, current.result).catch(() => undefined);
          }
        }
      }
    } catch (cause) {
      const errorText = cause instanceof Error ? cause.message : "Task not found.";
      try {
        const saved = (await listSavedTasks()).find((item) => item.id === taskId);
        if (!saved) throw new Error(errorText);
        setTask({
          id: saved.id,
          owner: user?.uid ?? "unknown",
          status: saved.status,
          progress: saved.progress,
          created_at: saved.created_at,
          updated_at: saved.updated_at,
          request: { url: saved.url, instruction: saved.instruction },
          result: null,
          error: saved.error,
          logs: [],
        });
        setLogs(await listTaskLogs(taskId));
        setResult(await getSavedTaskResult(taskId));
        setMessage("Backend task expired; showing the Supabase snapshot.");
      } catch {
        setMessage(errorText);
      }
    }
  }, [taskId, token, user]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [load]);

  async function handleCancel() {
    setBusy(true);
    try {
      await cancelTask(taskId, token);
      await load();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not cancel task.");
    } finally {
      setBusy(false);
    }
  }

  if (!task) {
    return (
      <div className="nex-card p-10 text-center">
        <p className="text-sm text-nex-muted">{message ?? "Loading task…"}</p>
        <Link href="/runs" className="mt-4 inline-block text-sm text-nex-accent">
          Back to tasks
        </Link>
      </div>
    );
  }

  const active = task.status === "queued" || task.status === "running";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/runs" className="text-xs text-nex-accent hover:underline">
            ← Tasks
          </Link>
          <h1 className="mt-2 text-2xl font-bold">Task detail</h1>
          <p className="mt-1 break-all font-mono text-xs text-nex-muted">{task.id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="nex-btn nex-btn-ghost"
            onClick={() => downloadJson(task, `nexora-task-${task.id}.json`)}
          >
            Export task JSON
          </button>
          {active ? (
            <button
              className="nex-btn nex-btn-danger"
              disabled={busy}
              onClick={() => void handleCancel()}
            >
              {busy ? "Cancelling…" : "Cancel task"}
            </button>
          ) : null}
        </div>
      </div>

      {message ? <p className="text-sm text-amber-200">{message}</p> : null}

      <section className="nex-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StatusBadge status={task.status} />
          <span className="text-xs text-nex-muted">
            Updated {new Date(task.updated_at).toLocaleString()}
          </span>
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/5">
          <div
            className="h-full rounded-full bg-gradient-to-r from-nex-accent to-nex-mint transition-all"
            style={{ width: `${task.progress}%` }}
          />
        </div>
        <div className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <div className="nex-label">Target</div>
            <div className="break-all">{task.request.url}</div>
          </div>
          <div>
            <div className="nex-label">Instruction</div>
            <div>{task.request.instruction}</div>
          </div>
        </div>
        {task.error ? (
          <p className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-200">
            {task.error}
          </p>
        ) : null}
      </section>

      <section className="nex-card p-5">
        <h2 className="mb-4 text-sm font-semibold">Execution log</h2>
        {logs.length === 0 ? (
          <p className="text-sm text-nex-muted">No log entries yet.</p>
        ) : (
          <ol className="space-y-3 text-sm">
            {logs.map((entry, index) => (
              <li key={`${entry.timestamp}-${index}`} className="flex gap-3">
                <span className="w-20 shrink-0 text-xs text-nex-muted">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
                <span
                  className={
                    entry.level === "error"
                      ? "text-rose-300"
                      : entry.level === "warn"
                        ? "text-amber-200"
                        : "text-white/80"
                  }
                >
                  {entry.message}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {result ? <ResultView result={result} title="Task result" taskId={task.id} /> : null}
    </div>
  );
}
