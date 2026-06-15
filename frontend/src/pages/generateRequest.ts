/** Merge selected and added questions: trim, drop empties, dedupe (case-sensitive), preserve order. */
export function resolveQuestions(selected: string[], added: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of [...selected, ...added]) {
    const q = raw.trim();
    if (!q || seen.has(q)) continue;
    seen.add(q);
    out.push(q);
  }
  return out;
}
