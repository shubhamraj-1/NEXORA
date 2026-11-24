/** Browser-side export helpers for results, tasks, and saved history. */

export function safeFileName(value: string): string {
  return value.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "nexora";
}

function download(content: BlobPart, filename: string, type: string): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function downloadJson(value: unknown, filename: string): void {
  download(JSON.stringify(value, null, 2), filename, "application/json");
}

function escapeCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function toCsv(headers: string[], rows: Array<Array<unknown>>): string {
  const lines = [headers.map(escapeCell).join(",")];
  for (const row of rows) lines.push(row.map(escapeCell).join(","));
  return `\uFEFF${lines.join("\r\n")}`;
}

export function downloadCsv(
  headers: string[],
  rows: Array<Array<unknown>>,
  filename: string,
): void {
  download(toCsv(headers, rows), filename, "text/csv;charset=utf-8");
}
