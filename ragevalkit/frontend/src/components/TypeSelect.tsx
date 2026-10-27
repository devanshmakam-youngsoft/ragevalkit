/** The two kinds of test case. Values found in older data (query, conversational…) are kept as they are. */
export const CASE_TYPES = [
  { value: "rag", label: "rag", hint: "The answer has to come from your documents, so retrieval is scored too." },
  { value: "non-rag", label: "non-rag", hint: "A greeting or small talk: no retrieval is expected, so only the answer is graded." },
] as const;

/** Type of a test case: rag or non-rag. An existing value that is neither stays selectable so nothing is silently changed. */
export function TypeSelect({ value, onChange, className = "" }: { value: string; onChange: (v: string) => void; className?: string }) {
  const known = CASE_TYPES.some((t) => t.value === value);
  const hint = CASE_TYPES.find((t) => t.value === value)?.hint;
  return (
    <select value={value || "rag"} onChange={(e) => onChange(e.target.value)} title={hint} aria-label="Type"
      className={`w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand ${className}`}>
      {CASE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
      {!known && value && <option value={value}>{value}</option>}
    </select>
  );
}
