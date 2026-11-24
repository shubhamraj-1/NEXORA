import { createClient, type User } from "@supabase/supabase-js";

import type {
  AgentRunResponse,
  TaskLog,
  TaskRecord,
  TaskStatus,
} from "@/lib/api";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const storageBucket = process.env.NEXT_PUBLIC_SUPABASE_STORAGE_BUCKET || "generated-files";

export type SupabaseUser = {
  uid: string;
  email: string | null;
  displayName: string | null;
};

export type SavedRun = {
  id: string;
  user_id: string;
  url: string;
  instruction: string;
  title: string | null;
  answer: string | null;
  plan: string[];
  model: string | null;
  status_code: number | null;
  elapsed_ms: number;
  created_at: string;
  result: Partial<AgentRunResponse> | null;
};

export type SavedTask = {
  id: string;
  status: TaskStatus;
  progress: number;
  url: string;
  instruction: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  synced_at: string;
};

export type SavedProfile = {
  uid: string;
  email: string | null;
  displayName: string | null;
  created_at: string;
  updated_at: string;
};

type ProfileRow = {
  id: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
  updated_at: string;
};

type RunRow = {
  id: string;
  user_id: string;
  url: string;
  instruction: string;
  title: string | null;
  answer: string | null;
  plan: string[] | null;
  model: string | null;
  status_code: number | null;
  elapsed_ms: number | null;
  created_at: string;
  result: Partial<AgentRunResponse> | null;
};

type TaskRow = {
  id: string;
  user_id: string;
  status: TaskStatus;
  progress: number | null;
  url: string;
  instruction: string;
  error: string | null;
  created_at: string;
  updated_at: string;
};

type TaskLogRow = {
  task_id: string;
  user_id: string;
  timestamp: string;
  level: string;
  message: string;
};

type TaskResultRow = {
  task_id: string;
  user_id: string;
  result: Partial<AgentRunResponse>;
  saved_at: string;
};

export function isSupabaseConfigured(): boolean {
  return Boolean(url && anonKey);
}

export function getSupabase() {
  if (!isSupabaseConfigured()) {
    throw new Error(
      "Supabase is not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to frontend/.env.local.",
    );
  }
  return createClient(url!, anonKey!);
}

function toUser(user: User | null): SupabaseUser | null {
  if (!user) return null;
  return {
    uid: user.id,
    email: user.email ?? null,
    displayName: (user.user_metadata?.display_name as string | undefined) ?? null,
  };
}

async function requireUserId(): Promise<string> {
  const supabase = getSupabase();
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) throw new Error("Sign in before saving data.");
  return data.user.id;
}

export function observeAuth(callback: (user: SupabaseUser | null) => void): () => void {
  if (!isSupabaseConfigured()) {
    callback(null);
    return () => {};
  }
  const supabase = getSupabase();
  const { data } = supabase.auth.onAuthStateChange((_event, session) => {
    callback(toUser(session?.user ?? null));
  });
  return () => data.subscription.unsubscribe();
}

export async function getIdToken(): Promise<string | null> {
  if (!isSupabaseConfigured()) return null;
  const { data } = await getSupabase().auth.getSession();
  return data.session?.access_token ?? null;
}

async function ensureProfile(user: User): Promise<void> {
  const supabase = getSupabase();
  await supabase.from("profiles").upsert(
    {
      id: user.id,
      email: user.email ?? null,
      display_name: (user.user_metadata?.display_name as string | undefined) ?? null,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "id" },
  );
}

export async function signIn(email: string, password: string): Promise<SupabaseUser> {
  const supabase = getSupabase();
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message);
  if (data.user) await ensureProfile(data.user);
  return toUser(data.user)!;
}

export async function signUp(email: string, password: string): Promise<SupabaseUser> {
  const supabase = getSupabase();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { display_name: email.split("@")[0] } },
  });
  if (error) throw new Error(error.message);
  if (data.user) await ensureProfile(data.user);
  return toUser(data.user)!;
}

export async function signOut(): Promise<void> {
  if (!isSupabaseConfigured()) return;
  const { error } = await getSupabase().auth.signOut();
  if (error) throw new Error(error.message);
}

export async function getProfile(): Promise<SavedProfile | null> {
  const userId = await requireUserId();
  const { data, error } = await getSupabase()
    .from("profiles")
    .select("id,email,display_name,created_at,updated_at")
    .eq("id", userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const row = data as ProfileRow;
  return {
    uid: row.id,
    email: row.email,
    displayName: row.display_name,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

export async function updateDisplayName(displayName: string): Promise<void> {
  const userId = await requireUserId();
  const supabase = getSupabase();
  const { error: authError } = await supabase.auth.updateUser({
    data: { display_name: displayName },
  });
  if (authError) throw new Error(authError.message);
  const { error } = await supabase
    .from("profiles")
    .update({ display_name: displayName, updated_at: new Date().toISOString() })
    .eq("id", userId);
  if (error) throw new Error(error.message);
}

function stripScreenshot(result: AgentRunResponse): Partial<AgentRunResponse> {
  const stored: Partial<AgentRunResponse> = { ...result };
  delete stored.screenshot_base64;
  return stored;
}

function runFromRow(row: RunRow): SavedRun {
  return {
    id: row.id,
    user_id: row.user_id,
    url: row.url,
    instruction: row.instruction,
    title: row.title,
    answer: row.answer,
    plan: row.plan ?? [],
    model: row.model,
    status_code: row.status_code,
    elapsed_ms: row.elapsed_ms ?? 0,
    created_at: row.created_at,
    result: row.result,
  };
}

export async function saveRun(result: AgentRunResponse): Promise<SavedRun> {
  const userId = await requireUserId();
  const { data, error } = await getSupabase()
    .from("runs")
    .insert({
      user_id: userId,
      url: result.url,
      instruction: result.instruction,
      title: result.title,
      answer: result.answer,
      plan: result.plan,
      model: result.model,
      status_code: result.status_code,
      elapsed_ms: result.elapsed_ms,
      result: stripScreenshot(result),
    })
    .select()
    .single();
  if (error) throw new Error(error.message);
  return runFromRow(data as RunRow);
}

export async function listRuns(): Promise<SavedRun[]> {
  const userId = await requireUserId();
  const { data, error } = await getSupabase()
    .from("runs")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(100);
  if (error) throw new Error(error.message);
  return (data as RunRow[]).map(runFromRow);
}

export async function deleteRun(id: string): Promise<void> {
  const userId = await requireUserId();
  const { error } = await getSupabase()
    .from("runs")
    .delete()
    .eq("id", id)
    .eq("user_id", userId);
  if (error) throw new Error(error.message);
}

export async function saveTaskSnapshot(task: TaskRecord): Promise<void> {
  const userId = await requireUserId();
  const { error } = await getSupabase().from("tasks").upsert(
    {
      id: task.id,
      user_id: userId,
      status: task.status,
      progress: task.progress,
      url: task.request.url,
      instruction: task.request.instruction,
      error: task.error,
      created_at: task.created_at,
      updated_at: task.updated_at,
    },
    { onConflict: "id" },
  );
  if (error) throw new Error(error.message);
}

export async function saveTaskLogs(taskId: string, logs: TaskLog[]): Promise<void> {
  const userId = await requireUserId();
  const supabase = getSupabase();
  const removed = await supabase
    .from("task_logs")
    .delete()
    .eq("task_id", taskId)
    .eq("user_id", userId);
  if (removed.error) throw new Error(removed.error.message);
  if (logs.length === 0) return;
  const payload: TaskLogRow[] = logs.map((entry) => ({
    task_id: taskId,
    user_id: userId,
    timestamp: entry.timestamp,
    level: entry.level,
    message: entry.message,
  }));
  const { error } = await supabase.from("task_logs").insert(payload);
  if (error) throw new Error(error.message);
}

export async function saveTaskResult(
  taskId: string,
  result: AgentRunResponse,
): Promise<void> {
  const userId = await requireUserId();
  const { error } = await getSupabase().from("task_results").upsert(
    {
      task_id: taskId,
      user_id: userId,
      result: stripScreenshot(result),
      saved_at: new Date().toISOString(),
    },
    { onConflict: "task_id" },
  );
  if (error) throw new Error(error.message);
}

function taskFromRow(row: TaskRow): SavedTask {
  return {
    id: row.id,
    status: row.status,
    progress: row.progress ?? 0,
    url: row.url,
    instruction: row.instruction,
    error: row.error,
    created_at: row.created_at,
    updated_at: row.updated_at,
    synced_at: row.updated_at,
  };
}

export async function listSavedTasks(): Promise<SavedTask[]> {
  const userId = await requireUserId();
  const { data, error } = await getSupabase()
    .from("tasks")
    .select("*")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false })
    .limit(100);
  if (error) throw new Error(error.message);
  return (data as TaskRow[]).map(taskFromRow);
}

export async function listTaskLogs(taskId: string): Promise<TaskLog[]> {
  const userId = await requireUserId();
  const { data, error } = await getSupabase()
    .from("task_logs")
    .select("timestamp,level,message")
    .eq("task_id", taskId)
    .eq("user_id", userId)
    .order("timestamp", { ascending: true });
  if (error) throw new Error(error.message);
  return (data as Array<Pick<TaskLogRow, "timestamp" | "level" | "message">>).map(
    (row) => ({ timestamp: row.timestamp, level: row.level, message: row.message }),
  );
}

export async function getSavedTaskResult(
  taskId: string,
): Promise<Partial<AgentRunResponse> | null> {
  const userId = await requireUserId();
  const { data, error } = await getSupabase()
    .from("task_results")
    .select("result")
    .eq("task_id", taskId)
    .eq("user_id", userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data ? (data as Pick<TaskResultRow, "result">).result : null;
}

export async function deleteSavedTask(taskId: string): Promise<void> {
  const userId = await requireUserId();
  const supabase = getSupabase();
  for (const table of ["task_logs", "task_results", "tasks"] as const) {
    const { error } = await supabase
      .from(table)
      .delete()
      .eq("user_id", userId)
      .eq(table === "tasks" ? "id" : "task_id", taskId);
    if (error) throw new Error(error.message);
  }
}

export async function uploadScreenshot(
  taskId: string,
  base64Png: string,
): Promise<string | null> {
  const userId = await requireUserId();
  const bytes = Uint8Array.from(atob(base64Png), (char) => char.charCodeAt(0));
  const path = `${userId}/${taskId}.png`;
  const supabase = getSupabase();
  const { error } = await supabase.storage
    .from(storageBucket)
    .upload(path, bytes, { contentType: "image/png", upsert: true });
  if (error) throw new Error(error.message);
  const { data, error: signError } = await supabase.storage
    .from(storageBucket)
    .createSignedUrl(path, 3600);
  if (signError) throw new Error(signError.message);
  return data.signedUrl;
}
