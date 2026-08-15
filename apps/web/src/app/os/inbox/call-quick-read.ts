export type CallQuickReadSource = {
  summary: string;
  motivation: string | null;
  timeline: string | null;
  asking_price: string | null;
  mortgage_balance: string | null;
  next_action: string | null;
};

export type CallQuickReadItem = {
  label: string;
  value: string;
};

const unexpectedCjkPattern =
  /[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]/;

function compactNote(value: string | null, maxLength: number) {
  if (!value) return null;
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized || unexpectedCjkPattern.test(normalized)) return null;

  const firstSentence = normalized.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? normalized;
  const candidate = firstSentence.length <= maxLength ? firstSentence : normalized;
  if (candidate.length <= maxLength) return candidate;

  const shortened = candidate.slice(0, maxLength + 1);
  const lastSpace = shortened.lastIndexOf(" ");
  const cutoff = lastSpace >= Math.floor(maxLength * 0.65) ? lastSpace : maxLength;
  return `${candidate.slice(0, cutoff).trimEnd()}...`;
}

function compactText(value: string | null, maxLength: number) {
  if (!value) return null;
  const normalized = value
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
  if (!normalized || unexpectedCjkPattern.test(normalized)) return null;
  if (normalized.length <= maxLength) return normalized;

  const shortened = normalized.slice(0, maxLength + 1);
  const lastSpace = shortened.lastIndexOf(" ");
  const cutoff = lastSpace >= Math.floor(maxLength * 0.65) ? lastSpace : maxLength;
  return `${normalized.slice(0, cutoff).trimEnd()}...`;
}

export function buildCallQuickRead(
  notes: CallQuickReadSource,
  quickReadSummary: string | null = null,
): CallQuickReadItem[] {
  const backendSummary = compactText(quickReadSummary, 800);
  if (backendSummary) {
    return [{ label: "Bottom line", value: backendSummary }];
  }

  const numbers = [
    notes.asking_price ? `Asking ${notes.asking_price}` : null,
    notes.mortgage_balance ? `Payoff ${notes.mortgage_balance}` : null,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" / ");

  return [
    {
      label: "Bottom line",
      value: compactNote(notes.summary, 190),
    },
    { label: "Why now", value: compactNote(notes.motivation, 150) },
    { label: "Timing", value: compactNote(notes.timeline, 130) },
    { label: "Numbers", value: numbers || null },
    { label: "Next step", value: compactNote(notes.next_action, 180) },
  ].filter((item): item is CallQuickReadItem => Boolean(item.value));
}
