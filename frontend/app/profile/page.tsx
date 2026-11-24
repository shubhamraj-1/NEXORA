"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import {
  getProfile,
  isSupabaseConfigured,
  updateDisplayName,
  type SavedProfile,
} from "@/lib/supabase";

export default function ProfilePage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<SavedProfile | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user || !isSupabaseConfigured()) return;
    try {
      const value = await getProfile();
      setProfile(value);
      setName(value?.displayName ?? "");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not load profile.");
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await updateDisplayName(name);
      await load();
      setMessage("Profile updated.");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Could not update profile.");
    } finally {
      setBusy(false);
    }
  }

  if (!isSupabaseConfigured() || !user) {
    return (
      <div className="nex-card p-12 text-center">
        <h1 className="text-xl font-semibold">Profile</h1>
        <p className="mx-auto mt-3 max-w-md text-sm text-nex-muted">
          Sign in with Supabase to view and update your profile.
        </p>
        <Link href="/settings" className="nex-btn nex-btn-primary mt-6">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Profile</h1>
        <p className="mt-2 text-sm text-nex-muted">
          Your Supabase identity and public profile row.
        </p>
      </div>

      <section className="nex-card p-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <div className="nex-label">UID</div>
            <div className="break-all font-mono text-xs">{user.uid}</div>
          </div>
          <div>
            <div className="nex-label">Email</div>
            <div className="text-sm">{user.email ?? "(none)"}</div>
          </div>
          <div>
            <div className="nex-label">Created</div>
            <div className="text-sm">
              {profile ? new Date(profile.created_at).toLocaleString() : "—"}
            </div>
          </div>
          <div>
            <div className="nex-label">Last updated</div>
            <div className="text-sm">
              {profile ? new Date(profile.updated_at).toLocaleString() : "—"}
            </div>
          </div>
        </div>
      </section>

      <section className="nex-card p-6">
        <h2 className="mb-4 text-sm font-semibold">Display name</h2>
        <form className="flex flex-wrap gap-3" onSubmit={handleSubmit}>
          <input
            className="nex-input max-w-sm"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Your name"
          />
          <button className="nex-btn nex-btn-primary" type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </form>
        {message ? <p className="mt-3 text-xs text-nex-muted">{message}</p> : null}
      </section>
    </div>
  );
}
