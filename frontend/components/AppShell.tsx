"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";

const NAV = [
  { href: "/", label: "Overview", icon: "◈" },
  { href: "/runs/new", label: "New run", icon: "＋" },
  { href: "/runs", label: "Tasks", icon: "≡" },
  { href: "/history", label: "Results", icon: "▤" },
  { href: "/settings", label: "Settings", icon: "⚙" },
  { href: "/profile", label: "Profile", icon: "◎" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, capabilities, supabaseReady, signOut } = useAuth();
  const [busy, setBusy] = useState(false);

  const aiConfigured = capabilities?.ai.configured ?? false;

  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-b border-nex-line bg-[#0a1020]/90 backdrop-blur lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between gap-3 px-5 py-5 lg:block">
          <Link href="/" className="block">
            <div className="text-xl font-bold tracking-[0.2em]">NEXORA</div>
            <div className="mt-1 text-[11px] text-nex-muted">
              From instructions to execution
            </div>
          </Link>
          <span className="nex-pill lg:mt-4">
            <span className={aiConfigured ? "nex-dot" : "nex-dot nex-dot-off"} />
            {aiConfigured ? "AI online" : "AI optional"}
          </span>
        </div>

        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:mt-4 lg:flex-col lg:overflow-visible">
          {NAV.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${
                  active
                    ? "bg-nex-accent/15 text-white ring-1 ring-nex-accent/40"
                    : "text-nex-muted hover:bg-white/5 hover:text-white"
                }`}
              >
                <span className="text-base leading-none">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden px-5 py-5 text-xs leading-relaxed text-nex-muted lg:block">
          <div className="mb-2 font-semibold text-white/80">Runtime</div>
          <div>Chromium · Playwright</div>
          <div>Supabase Auth + Postgres</div>
          <div>
            Rate limit: {capabilities?.limits.rate_limit_per_minute ?? "—"}/min
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 border-b border-nex-line bg-nex-bg/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3">
            <div className="text-sm text-nex-muted">
              <span className="text-white">Workspace</span>
              <span className="mx-2">/</span>
              {NAV.find((item) =>
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href),
              )?.label ?? "NEXORA"}
            </div>
            <div className="flex items-center gap-2">
              <span className="nex-pill hidden sm:inline-flex">
                <span className={supabaseReady ? "nex-dot" : "nex-dot nex-dot-off"} />
                {supabaseReady ? "Supabase ready" : "Local mode"}
              </span>
              {user ? (
                <>
                  <Link href="/profile" className="nex-pill max-w-48 truncate">
                    {user.displayName || user.email || user.uid}
                  </Link>
                  <button
                    type="button"
                    className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await signOut();
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <Link href="/settings" className="nex-btn nex-btn-primary !px-3 !py-2 text-xs">
                  Sign in
                </Link>
              )}
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
      </div>
    </div>
  );
}
