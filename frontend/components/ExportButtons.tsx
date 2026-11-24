"use client";

import type { AgentRunResponse } from "@/lib/api";
import { downloadCsv, downloadJson, safeFileName } from "@/lib/exports";
import type { SavedRun } from "@/lib/supabase";

export function ResultExports({
  result,
  label = "result",
}: {
  result: AgentRunResponse | Partial<AgentRunResponse>;
  label?: string;
}) {
  const base = safeFileName(`${label}-${result.title || "nexora"}`);

  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
        onClick={() => downloadJson(result, `${base}.json`)}
      >
        Export JSON
      </button>
      <button
        type="button"
        className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
        onClick={() =>
          downloadCsv(
            ["Action", "Detail", "Duration ms"],
            (result.steps ?? []).map((step) => [
              step.action,
              step.detail,
              step.duration_ms,
            ]),
            `${base}-steps.csv`,
          )
        }
      >
        Steps CSV
      </button>
      <button
        type="button"
        className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
        onClick={() =>
          downloadCsv(
            ["Text", "Href"],
            (result.links ?? []).map((link) => [link.text, link.href]),
            `${base}-links.csv`,
          )
        }
      >
        Links CSV
      </button>
    </div>
  );
}

export function RunHistoryExports({ runs }: { runs: SavedRun[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
        disabled={runs.length === 0}
        onClick={() =>
          downloadCsv(
            ["Created", "Title", "URL", "Instruction", "Answer", "Status", "Elapsed ms"],
            runs.map((run) => [
              run.created_at,
              run.title ?? "",
              run.url,
              run.instruction,
              run.answer ?? "",
              run.status_code ?? "",
              run.elapsed_ms,
            ]),
            "nexora-history.csv",
          )
        }
      >
        Export history CSV
      </button>
      <button
        type="button"
        className="nex-btn nex-btn-ghost !px-3 !py-2 text-xs"
        disabled={runs.length === 0}
        onClick={() => downloadJson(runs, "nexora-history.json")}
      >
        Export history JSON
      </button>
    </div>
  );
}
