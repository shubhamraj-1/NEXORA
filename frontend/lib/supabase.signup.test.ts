import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  signUp: vi.fn(),
  upsert: vi.fn(),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: { signUp: mocks.signUp },
    from: () => ({ upsert: mocks.upsert }),
  }),
}));

function user() {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    email: "tester@example.com",
    user_metadata: { display_name: "tester" },
  };
}

describe("Supabase sign-up", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("requires email confirmation without writing a profile", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "public-test-key");
    mocks.signUp.mockResolvedValue({
      data: { user: user(), session: null },
      error: null,
    });

    const { signUp } = await import("@/lib/supabase");
    const result = await signUp("tester@example.com", "password");

    expect(result.needsEmailConfirmation).toBe(true);
    expect(mocks.upsert).not.toHaveBeenCalled();
  });

  it("writes a profile when Supabase returns a session", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "public-test-key");
    mocks.signUp.mockResolvedValue({
      data: { user: user(), session: { access_token: "token" } },
      error: null,
    });
    mocks.upsert.mockResolvedValue({ error: null });

    const { signUp } = await import("@/lib/supabase");
    const result = await signUp("tester@example.com", "password");

    expect(result.needsEmailConfirmation).toBe(false);
    expect(mocks.upsert).toHaveBeenCalledOnce();
  });
});
