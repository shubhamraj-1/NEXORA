"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { cancelTask, listTasks, type TaskRecord } from "@/lib/api";
import { listSavedTasks, saveTaskSnapshot } from "@/lib/supabase";

export default function TasksPage() {
  const { user, token, supabaseReady } = useAuth();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const activeRef = useRef(false);
  const loaded = useRef(false);

  const load = useCallback(
    async (force = false) => {
      if (inFlight.current || (!force && loaded.current && !activeRef.current)) return;
      inFlight.current = true;
      loaded.current = true;
      try {
        setMessage(null);
        let backend: TaskRecord[] = [];
        try {
          backend = await listTasks(token);
        } catch (cause) {
          setMessage(cause instanceof Error ? cause.message : "Could not load backend tasks.");
        }
        activeRef.current = backend.some(
          (task) => task.status === "queued" || task.status === "running",
        );
        setTasks(backend);

        if (user && supabaseReady) {
          try {
            const saved = await listSavedTasks();
            const known = new Set(backend.map((task) => task.id));
            const restored = saved
              .filter((item) => !known.has(item.id))
              .map<TaskRecord>((item) => ({
                id: item.id,
                owner: user.uid,
                status: item.status,
                progress: item.progress,
                created_at: item.created_at,
                updated_at: item.updated_at,
                request: { url: item.url, instruction: item.instruction },
                result: null,
                error: item.error,
                logs: [],
              }));
            setTasks([...backend, ...restored]);
          } catch {
            // Supabase is optional for display.
          }
        }
      } finally {
        inFlight.current = false;
      }
    },
    [token, user, supabaseReady],
  );

  useEffect(() => {
    void load(true);
    const timer = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function handleCancel(taskId: string) {
    setBusyId(taskId);
    try {
      const updated = await cancelTask(taskId, token);
      if (user) await saveTaskSnapshot(updated).catch(() => undefined);
      await load(true);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not cancel task.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Tasks</h1>
          <p className="mt-2 text-sm text-nex-muted">
            Live queue with status, progress, cancellation, and result access.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="nex-btn nex-btn-ghost" onClick={() => void load(true)}>
            Refresh
          </button>
          <Link href="/runs/new" className="nex-btn nex-btn-primary">
            New task
          </Link>
        </div>
      </div>

      {message ? <p className="text-sm text-nex-danger">{message}</p> : null}

      {tasks.length === 0 ? (
        <div className="nex-card p-12 text-center">
          <p className="text-sm text-nex-muted">No tasks found.</p>
          <Link href="/runs/new" className="mt-3 inline-block text-sm text-nex-accent">
            Launch one now
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => {
            const active = task.status === "queued" || task.status === "running";
            return (
              <div key={task.id} className="nex-card p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-3">
                      <StatusBadge status={task.status} />
                      <span className="text-xs text-nex-muted">
                        {new Date(task.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-3 truncate text-sm font-medium">{task.request.url}</p>
                    <p className="mt-1 truncate text-sm text-nex-muted">
                      {task.request.instruction}
                    </p>
                    {task.error ? (
                      <p className="mt-2 text-xs text-nex-danger">{task.error}</p>
                    ) : null}
                  </div>
                  <div className="flex gap-2">
                    <Link
                      href={`/runs/${task.id}`}
                      className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
                    >
                      Open
                    </Link>
                    {active ? (
                      <button
                        className="nex-btn nex-btn-danger !px-3 !py-2 text-xs"
                        disabled={busyId === task.id}
                        onClick={() => void handleCancel(task.id)}
                      >
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-nex-accent transition-all"
                    style={{ width: `${task.progress}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
