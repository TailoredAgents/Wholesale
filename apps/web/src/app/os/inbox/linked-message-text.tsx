import { Fragment, type ReactNode } from "react";

const LINK_PATTERN = /\b(?:https?:\/\/|www\.)[^\s<>"']+/gi;
const SIMPLE_TRAILING_PUNCTUATION = new Set([".", ",", "!", "?", ";", ":"]);
const CLOSING_DELIMITERS: Record<string, string> = {
  ")": "(",
  "]": "[",
  "}": "{",
};

const EMAIL_TRAILING_CONTENT_PATTERNS = [
  { pattern: /\n--\s*\n/, summary: "Show signature" },
  {
    pattern: /\nSent from (?:my |Yahoo Mail|Mail for iPhone)/i,
    summary: "Show signature and quoted history",
  },
  { pattern: /\nOn .{1,320}wrote:\s*\n/i, summary: "Show quoted message" },
  { pattern: /\n-{2,}\s*Original Message\s*-{2,}/i, summary: "Show quoted message" },
  {
    pattern: /\nFrom:\s*[^\n]+\nSent:\s*[^\n]+\nTo:\s*[^\n]+/i,
    summary: "Show quoted message",
  },
];

function countCharacter(value: string, character: string): number {
  return [...value].filter((item) => item === character).length;
}

function splitTrailingPunctuation(value: string) {
  let link = value;
  let trailing = "";

  while (link.length > 0) {
    const finalCharacter = link.at(-1) as string;
    if (SIMPLE_TRAILING_PUNCTUATION.has(finalCharacter)) {
      trailing = finalCharacter + trailing;
      link = link.slice(0, -1);
      continue;
    }

    const openingDelimiter = CLOSING_DELIMITERS[finalCharacter];
    if (
      openingDelimiter &&
      countCharacter(link, finalCharacter) > countCharacter(link, openingDelimiter)
    ) {
      trailing = finalCharacter + trailing;
      link = link.slice(0, -1);
      continue;
    }
    break;
  }

  return { link, trailing };
}

function safeHref(value: string): string | null {
  const candidate = value.toLowerCase().startsWith("www.")
    ? `https://${value}`
    : value;
  try {
    const parsed = new URL(candidate);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      !parsed.hostname ||
      parsed.username ||
      parsed.password
    ) {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

function displayLink(value: string, href: string) {
  if (value.length <= 54) return value;
  const parsed = new URL(href);
  const path = parsed.pathname === "/" ? "" : parsed.pathname;
  const shortenedPath = path.length > 24 ? `${path.slice(0, 24)}...` : path;
  return `${parsed.hostname}${shortenedPath}`;
}

function linkedContent(text: string) {
  const content: ReactNode[] = [];
  let cursor = 0;

  for (const match of text.matchAll(LINK_PATTERN)) {
    const index = match.index;
    if (index === undefined) continue;
    if (index > cursor) content.push(text.slice(cursor, index));

    const matchedValue = match[0];
    const { link, trailing } = splitTrailingPunctuation(matchedValue);
    const href = safeHref(link);
    if (href) {
      content.push(
        <a
          href={href}
          key={`${index}-${link}`}
          rel="noopener noreferrer"
          target="_blank"
          title={link}
        >
          {displayLink(link, href)}
        </a>,
      );
      if (trailing) content.push(trailing);
    } else {
      content.push(matchedValue);
    }
    cursor = index + matchedValue.length;
  }

  if (cursor < text.length) content.push(text.slice(cursor));
  return content.map((item, index) => <Fragment key={index}>{item}</Fragment>);
}

function splitEmailTrailingContent(text: string) {
  let earliestIndex = -1;
  let summary = "Show quoted message";

  for (const candidate of EMAIL_TRAILING_CONTENT_PATTERNS) {
    const match = candidate.pattern.exec(text);
    if (match && (earliestIndex === -1 || match.index < earliestIndex)) {
      earliestIndex = match.index;
      summary = candidate.summary;
    }
  }

  if (earliestIndex <= 0) return { current: text, trailing: "", summary };
  return {
    current: text.slice(0, earliestIndex).trimEnd(),
    trailing: text.slice(earliestIndex).trim(),
    summary,
  };
}

export function LinkedMessageText({
  collapseEmailHistory = false,
  text,
}: {
  collapseEmailHistory?: boolean;
  text: string;
}) {
  const { current, trailing, summary } = collapseEmailHistory
    ? splitEmailTrailingContent(text)
    : { current: text, trailing: "", summary: "Show quoted message" };

  return (
    <>
      {linkedContent(current)}
      {trailing ? (
        <details>
          <summary>{summary}</summary>
          <div>{linkedContent(trailing)}</div>
        </details>
      ) : null}
    </>
  );
}
