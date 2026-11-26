import { afterEach, describe, expect, it, vi } from "vitest";

describe("Supabase client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("reuses a single client instance", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "public-test-key");

    const { getSupabase } = await import("@/lib/supabase");

    expect(getSupabase()).toBe(getSupabase());
  });
});
