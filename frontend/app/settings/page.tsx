"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";

export default function SettingsPage() {
  const { user, supabaseReady, capabilities, signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      if (mode === "signup") {
        const result = await signUp(email, password);
        setMessage(
          result.needsEmailConfirmation
            ? "Check your email to confirm your account, then sign in."
            : "Account created and signed in.",
        );
      } else {
        await signIn(email, password);
        setMessage("Signed in.");
      }
      setPassword("");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="mt-2 text-sm text-nex-muted">
            Authentication and deployment configuration.
          </p>
        </div>

        <section className="nex-card p-6">
          <h2 className="mb-4 text-sm font-semibold">Supabase authentication</h2>
          {!supabaseReady ? (
            <div className="space-y-3 text-sm text-nex-muted">
              <p>Supabase web config is missing. Add these to frontend/.env.local:</p>
              <pre className="overflow-x-auto rounded-xl bg-black/30 p-4 text-xs">
{`NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_SUPABASE_STORAGE_BUCKET=generated-files`}
              </pre>
              <p>The app still works in open local mode without Supabase.</p>
            </div>
          ) : user ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-4 text-sm">
                Signed in as <strong>{user.email ?? user.uid}</strong>
              </div>
              <Link href="/profile" className="nex-btn nex-btn-ghost">
                Manage profile
              </Link>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={handleAuth}>
              <div className="flex gap-2">
                <button
                  type="button"
                  className={`nex-btn flex-1 !py-2 text-xs ${
                    mode === "signin" ? "nex-btn-primary" : "nex-btn-ghost"
                  }`}
                  onClick={() => setMode("signin")}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  className={`nex-btn flex-1 !py-2 text-xs ${
                    mode === "signup" ? "nex-btn-primary" : "nex-btn-ghost"
                  }`}
                  onClick={() => setMode("signup")}
                >
                  Sign up
                </button>
              </div>
              <input
                className="nex-input"
                type="email"
                required
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <input
                className="nex-input"
                type="password"
                required
                minLength={6}
                placeholder="Password (6+ characters)"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button className="nex-btn nex-btn-primary w-full" type="submit" disabled={busy}>
                {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
              </button>
              {message ? <p className="text-xs text-nex-muted">{message}</p> : null}
            </form>
          )}
        </section>
      </div>

      <div className="space-y-4">
        <section className="nex-card p-6">
          <h2 className="mb-4 text-sm font-semibold">Runtime configuration</h2>
          <SettingRow
            label="Backend auth required"
            value={capabilities?.auth.required ? "yes (Supabase)" : "no (local mode)"}
          />
          <SettingRow
            label="Browser"
            value={capabilities?.browser.engine ?? "checking"}
          />
          <SettingRow
            label="AI provider"
            value={
              capabilities?.ai.configured
                ? `OpenAI · ${capabilities.ai.model}`
                : "not configured"
            }
          />
          <SettingRow
            label="Rate limit"
            value={`${capabilities?.limits.rate_limit_per_minute ?? "—"} requests/minute`}
          />
          <SettingRow label="Max timeout" value={`${capabilities?.limits.max_timeout_ms ?? "—"} ms`} />
        </section>

        <section className="nex-card p-6">
          <h2 className="mb-3 text-sm font-semibold">Security posture</h2>
          <ul className="space-y-2 text-xs leading-6 text-nex-muted">
            <li>• Private, loopback, link-local, and metadata URLs are blocked.</li>
            <li>• Only public http(s) URLs on ports 80 and 443 are accepted.</li>
            <li>• Supabase access tokens are verified server-side with JWT secret or JWKS.</li>
            <li>• Postgres RLS scopes every user to their own rows.</li>
            <li>• Service role keys stay on the backend; the browser uses the anon key only.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-nex-line/60 py-2 text-sm last:border-0">
      <span className="text-nex-muted">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}
