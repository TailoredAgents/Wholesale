export const CALL_PLAYBACK_RATES = [0.75, 1, 1.25, 1.5, 2] as const;

export type CallPlaybackSession = {
  position: number;
  rate: number;
};

export function clampPlaybackTime(value: number, duration: number) {
  const safeValue = Number.isFinite(value) ? value : 0;
  const safeDuration = Number.isFinite(duration) && duration > 0 ? duration : 0;
  if (!safeDuration) return Math.max(0, safeValue);
  return Math.min(Math.max(0, safeValue), safeDuration);
}

export function skipPlaybackTime(current: number, delta: number, duration: number) {
  return clampPlaybackTime(current + delta, duration);
}

export function formatPlaybackTime(value: number) {
  const totalSeconds = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds
      .toString()
      .padStart(2, "0")}`;
  }
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function playbackAriaValue(current: number, duration: number) {
  return `${formatSpokenTime(current)} of ${formatSpokenTime(duration)}`;
}

export function parseCallPlaybackSession(value: string | null, duration: number) {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<CallPlaybackSession>;
    if (typeof parsed.position !== "number" || typeof parsed.rate !== "number") return null;
    if (
      !Number.isFinite(parsed.position) ||
      !(CALL_PLAYBACK_RATES as readonly number[]).includes(parsed.rate)
    ) {
      return null;
    }
    const safeDuration = Number.isFinite(duration) && duration > 0 ? duration : 0;
    const position = clampPlaybackTime(parsed.position, safeDuration);
    if (safeDuration && position >= safeDuration - 2) return { position: 0, rate: parsed.rate };
    return { position, rate: parsed.rate };
  } catch {
    return null;
  }
}

function formatSpokenTime(value: number) {
  const totalSeconds = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts = [];
  if (hours) parts.push(`${hours} ${hours === 1 ? "hour" : "hours"}`);
  if (minutes) parts.push(`${minutes} ${minutes === 1 ? "minute" : "minutes"}`);
  if (seconds || parts.length === 0) parts.push(`${seconds} ${seconds === 1 ? "second" : "seconds"}`);
  return parts.join(" ");
}
