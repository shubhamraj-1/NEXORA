export type AgentStep = {
  action: string;
  detail: string;
  duration_ms: number;
};

export type ExtractedLink = {
  text: string;
  href: string;
};

export type AgentRunRequest = {
  url: string;
  instruction: string;
  include_screenshot?: boolean;
  max_links?: number;
  timeout_ms?: number;
  ai?: boolean;
};

export type AgentRunResponse = {
  url: string;
  final_url: string;
  title: string;
  description: string;
  status_code: number | null;
  instruction: string;
  text: string;
  text_truncated: boolean;
  headings: string[];
  links: ExtractedLink[];
  screenshot_base64: string | null;
  steps: AgentStep[];
  elapsed_ms: number;
  plan: string[];
  answer: string | null;
  model: string | null;
};

export type TaskStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type TaskLog = {
  timestamp: string;
  level: string;
  message: string;
};

export type TaskRecord = {
  id: string;
  owner: string;
  status: TaskStatus;
  progress: number;
  created_at: string;
  updated_at: string;
  request: AgentRunRequest;
  result: AgentRunResponse | null;
  error: string | null;
  logs: TaskLog[];
};

export type Capabilities = {
  browser: { engine: string; headless: boolean; reused_across_requests: boolean };
  ai: { configured: boolean; provider: string; model: string | null };
  auth: { required: boolean; provider: string | null };
  tasks: {
    enabled: boolean;
    statuses: TaskStatus[];
    cancellable: boolean;
  };
  limits: {
    max_text_chars: number;
    max_links: number;
    max_timeout_ms: number;
    rate_limit_per_minute: number;
  };
};

async function parseError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((item) =>
            typeof item === "object" && item !== null && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : JSON.stringify(item),
          )
          .join("; ");
      }
    }
    return JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

function authHeaders(token?: string | null): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...init });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as T;
}

export function fetchCapabilities(): Promise<Capabilities> {
  return requestJson<Capabilities>("/api/v1/agent/capabilities");
}

export function runAgent(
  input: AgentRunRequest,
  token?: string | null,
): Promise<AgentRunResponse> {
  return requestJson<AgentRunResponse>("/api/v1/agent/run", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(input),
  });
}

export function createTask(
  input: AgentRunRequest,
  token?: string | null,
): Promise<TaskRecord> {
  return requestJson<TaskRecord>("/api/v1/tasks", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(input),
  });
}

export function listTasks(token?: string | null): Promise<TaskRecord[]> {
  return requestJson<TaskRecord[]>("/api/v1/tasks", {
    headers: authHeaders(token),
  });
}

export function getTask(
  taskId: string,
  token?: string | null,
): Promise<TaskRecord> {
  return requestJson<TaskRecord>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(token),
  });
}

export function getTaskLogs(
  taskId: string,
  token?: string | null,
): Promise<TaskLog[]> {
  return requestJson<TaskLog[]>(
    `/api/v1/tasks/${encodeURIComponent(taskId)}/logs`,
    { headers: authHeaders(token) },
  );
}

export function getTaskResult(
  taskId: string,
  token?: string | null,
): Promise<AgentRunResponse> {
  return requestJson<AgentRunResponse>(
    `/api/v1/tasks/${encodeURIComponent(taskId)}/result`,
    { headers: authHeaders(token) },
  );
}

export function cancelTask(
  taskId: string,
  token?: string | null,
): Promise<TaskRecord> {
  return requestJson<TaskRecord>(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
}
