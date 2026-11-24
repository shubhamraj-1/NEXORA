export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: "border-amber-400/40 bg-amber-400/10 text-amber-200",
    running: "border-sky-400/40 bg-sky-400/10 text-sky-200",
    succeeded: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
    failed: "border-rose-400/40 bg-rose-400/10 text-rose-200",
    cancelled: "border-slate-400/40 bg-slate-400/10 text-slate-200",
  };
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold capitalize ${
        styles[status] ?? "border-nex-line bg-white/5 text-nex-muted"
      }`}
    >
      <span className="nex-dot" />
      {status}
    </span>
  );
}
