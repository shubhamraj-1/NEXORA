"use client";

import { useState } from "react";

import type { AgentRunResponse } from "@/lib/api";
import { ResultExports } from "@/components/ExportButtons";
import { useAuth } from "@/components/AuthProvider";
import { uploadScreenshot } from "@/lib/supabase";

export function ResultView({
  result,
  title = "Result",
  taskId,
}: {
  result: AgentRunResponse | Partial<AgentRunResponse>;
  title?: string;
  taskId?: string;
}) {
  const { user } = useAuth();
  const [storageMessage, setStorageMessage] = useState<string | null>(null);
  const steps = result.steps ?? [];
  const links = result.links ?? [];
  const text = result.text ?? "";
  const plan = result.plan ?? [];

  return (
    <div className="space-y-4">
      <section className="nex-card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="flex flex-col items-end gap-2">
            <ResultExports result={result} />
            {user && taskId && result.screenshot_base64 ? (
              <button
                type="button"
                className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
                onClick={async () => {
                  setStorageMessage("Uploading…");
                  try {
                    await uploadScreenshot(taskId, result.screenshot_base64!);
                    setStorageMessage("Screenshot saved to Supabase Storage.");
                  } catch (cause) {
                    setStorageMessage(
                      cause instanceof Error ? cause.message : "Upload failed.",
                    );
                  }
                }}
              >
                Save screenshot to Storage
              </button>
            ) : null}
            {storageMessage ? (
              <span className="text-xs text-nex-muted">{storageMessage}</span>
            ) : null}
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Title" value={result.title || "(untitled)"} />
          <Metric label="HTTP" value={result.status_code ?? "n/a"} />
          <Metric label="Elapsed" value={`${result.elapsed_ms ?? 0} ms`} />
          <Metric label="Links" value={links.length} />
        </div>
        <p className="mt-4 break-all text-xs text-nex-muted">
          {result.final_url ?? result.url ?? ""}
        </p>
      </section>

      {result.answer ? (
        <section className="nex-card p-5">
          <h3 className="mb-3 text-sm font-semibold text-white/90">
            Answer{result.model ? ` · ${result.model}` : ""}
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-7 text-white/85">
            {result.answer}
          </p>
        </section>
      ) : null}

      {plan.length > 0 ? (
        <section className="nex-card p-5">
          <h3 className="mb-3 text-sm font-semibold text-white/90">Plan</h3>
          <ol className="space-y-2 text-sm text-white/80">
            {plan.map((step, index) => (
              <li key={`${index}-${step}`} className="flex gap-3">
                <span className="text-nex-accent">{index + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="nex-card overflow-hidden">
        <div className="border-b border-nex-line px-5 py-4 text-sm font-semibold">
          Execution trace
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-nex-muted">
              <tr>
                <th className="px-5 py-3">Action</th>
                <th className="px-5 py-3">Detail</th>
                <th className="px-5 py-3 text-right">Time</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step, index) => (
                <tr key={`${step.action}-${index}`} className="border-t border-nex-line/70">
                  <td className="px-5 py-3 font-medium">{step.action}</td>
                  <td className="px-5 py-3 text-white/70">{step.detail}</td>
                  <td className="px-5 py-3 text-right text-nex-muted">
                    {step.duration_ms} ms
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {links.length > 0 ? (
        <section className="nex-card p-5">
          <h3 className="mb-3 text-sm font-semibold">Extracted links</h3>
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            {links.slice(0, 40).map((link) => (
              <li key={link.href} className="truncate">
                <a
                  className="text-nex-accent hover:underline"
                  href={link.href}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {link.text || link.href}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="nex-card p-5">
        <h3 className="mb-3 text-sm font-semibold">Extracted text</h3>
        <details className="text-sm">
          <summary className="cursor-pointer text-nex-muted">
            {text.length} characters{result.text_truncated ? " (truncated)" : ""}
          </summary>
          <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-black/30 p-4 text-xs text-white/70">
            {text || "(empty)"}
          </pre>
        </details>
      </section>

      {result.screenshot_base64 ? (
        <section className="nex-card p-5">
          <h3 className="mb-3 text-sm font-semibold">Screenshot</h3>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="w-full rounded-xl border border-nex-line"
            alt={`Screenshot of ${result.final_url ?? result.url ?? "page"}`}
            src={`data:image/png;base64,${result.screenshot_base64}`}
          />
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-nex-line bg-black/20 p-3">
      <div className="text-[11px] uppercase tracking-wider text-nex-muted">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold text-white">{value}</div>
    </div>
  );
}
