import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createTask, fetchCapabilities, getTask, runAgent } from "@/lib/api";

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("frontend API client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests capabilities without caching", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ object: "list" }));

    await fetchCapabilities();

    expect(fetch).toHaveBeenCalledWith("/api/v1/agent/capabilities", {
      cache: "no-store",
    });
  });

  it("sends the bearer token and JSON body when creating a task", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "task-1" }));

    await createTask(
      { url: "https://example.com", instruction: "Summarize" },
      "local-test-token",
    );

    const [path, init] = vi.mocked(fetch).mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(path).toBe("/api/v1/tasks");
    expect(init?.method).toBe("POST");
    expect(headers.Authorization).toBe("Bearer local-test-token");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      url: "https://example.com",
      instruction: "Summarize",
    });
  });

  it("encodes task ids and omits auth headers without a token", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "task-1" }));

    await getTask("a/b c", null);

    const [path, init] = vi.mocked(fetch).mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(path).toBe("/api/v1/tasks/a%2Fb%20c");
    expect(headers.Authorization).toBeUndefined();
  });

  it("surfaces the API error detail", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: "bad request" }, { status: 400, statusText: "Bad Request" }),
    );

    await expect(
      runAgent({ url: "https://example.com", instruction: "x" }),
    ).rejects.toThrow("bad request");
  });
});
