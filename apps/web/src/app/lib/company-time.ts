export const COMPANY_TIME_ZONE = "America/New_York";
export const COMPANY_TIME_ZONE_LABEL = "ET";

type Timestamp = string | number | Date | null | undefined;

function parsedDate(value: Timestamp) {
  if (value == null || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatCompanyTimestamp(
  value: Timestamp,
  options: Intl.DateTimeFormatOptions,
  fallback = "Not set",
) {
  const date = parsedDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat("en-US", {
    ...options,
    timeZone: COMPANY_TIME_ZONE,
  }).format(date);
}

export function formatCompanyTime(value: Timestamp, fallback = "Unscheduled") {
  return formatCompanyTimestamp(
    value,
    { hour: "numeric", minute: "2-digit", timeZoneName: "short" },
    fallback,
  );
}

export function formatCompanyDateTime(value: Timestamp, fallback = "Unscheduled") {
  return formatCompanyTimestamp(
    value,
    {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    },
    fallback,
  );
}

export function formatCompanyDate(value: Timestamp, fallback = "Not set") {
  return formatCompanyTimestamp(
    value,
    { month: "short", day: "numeric", year: "numeric" },
    fallback,
  );
}

function companyParts(value: Date) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: COMPANY_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

export function companyDateKey(value: Timestamp) {
  const date = parsedDate(value);
  if (!date) return null;
  const parts = companyParts(date);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function companyDateTimeInputValue(value: Timestamp = new Date()) {
  const date = parsedDate(value);
  if (!date) return "";
  const parts = companyParts(date);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function timeZoneOffsetMilliseconds(value: Date) {
  const parts = companyParts(value);
  const renderedAsUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  );
  return renderedAsUtc - Math.floor(value.getTime() / 1000) * 1000;
}

export function companyDateTimeInputToIso(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Enter a valid Eastern date and time.");
  const [, year, month, day, hour, minute] = match;
  const wallClockUtc = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
  );
  let candidate = new Date(wallClockUtc);
  candidate = new Date(wallClockUtc - timeZoneOffsetMilliseconds(candidate));
  candidate = new Date(wallClockUtc - timeZoneOffsetMilliseconds(candidate));
  if (companyDateTimeInputValue(candidate) !== value) {
    throw new Error("That Eastern time does not exist because of daylight saving time.");
  }
  return candidate.toISOString();
}
