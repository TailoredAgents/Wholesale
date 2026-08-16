import { Fragment, type ReactNode } from "react";

const LINK_PATTERN = /\b(?:https?:\/\/|www\.)[^\s<>"']+/gi;
const SIMPLE_TRAILING_PUNCTUATION = new Set([".", ",", "!", "?", ";", ":"]);
const CLOSING_DELIMITERS: Record<string, string> = {
  ")": "(",
  "]": "[",
  "}": "{",
};

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

export function LinkedMessageText({ text }: { text: string }) {
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
          title="Open link in a new tab"
        >
          {link}
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
