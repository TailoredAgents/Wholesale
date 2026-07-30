import type { ReactNode } from "react";

import styles from "./help.module.css";

type AnswerBlock =
  | { type: "heading"; content: string }
  | { type: "paragraph"; content: string }
  | { type: "ordered-list"; items: string[] }
  | { type: "unordered-list"; items: string[] };

type FormattedHelpAnswerProps = {
  answer: string;
  citationCount: number;
  onCitationSelect: (index: number) => void;
};

const orderedItem = /^\s*\d+\.\s+(.+?)\s*$/;
const unorderedItem = /^\s*[-*]\s+(.+?)\s*$/;
const heading = /^\s*#{1,4}\s+(.+?)\s*$/;
const inlineToken = /(\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[(\d+)\]|\*([^*\n]+)\*)/g;

function isBlockStart(line: string) {
  return orderedItem.test(line) || unorderedItem.test(line) || heading.test(line);
}

export function parseHelpAnswer(answer: string): AnswerBlock[] {
  const lines = answer.replace(/\r\n?/g, "\n").split("\n");
  const blocks: AnswerBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const headingMatch = line.match(heading);
    if (headingMatch) {
      blocks.push({ type: "heading", content: headingMatch[1] });
      index += 1;
      continue;
    }

    const orderedMatch = line.match(orderedItem);
    if (orderedMatch) {
      const items: string[] = [];
      while (index < lines.length) {
        const current = lines[index].trim();
        if (!current) {
          const next = lines[index + 1]?.trim() ?? "";
          if (next.match(orderedItem)) {
            index += 1;
            continue;
          }
          break;
        }
        const match = current.match(orderedItem);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ type: "ordered-list", items });
      continue;
    }

    const unorderedMatch = line.match(unorderedItem);
    if (unorderedMatch) {
      const items: string[] = [];
      while (index < lines.length) {
        const current = lines[index].trim();
        if (!current) {
          const next = lines[index + 1]?.trim() ?? "";
          if (next.match(unorderedItem)) {
            index += 1;
            continue;
          }
          break;
        }
        const match = current.match(unorderedItem);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ type: "unordered-list", items });
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (index < lines.length) {
      const current = lines[index].trim();
      if (!current || isBlockStart(current)) break;
      paragraphLines.push(current);
      index += 1;
    }
    blocks.push({ type: "paragraph", content: paragraphLines.join(" ") });
  }

  return blocks;
}

function inlineContent(
  content: string,
  citationCount: number,
  onCitationSelect: (index: number) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  for (const match of content.matchAll(inlineToken)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(content.slice(cursor, start));

    if (match[2]) {
      nodes.push(<strong key={`${start}-strong`}>{match[2]}</strong>);
    } else if (match[3]) {
      nodes.push(<code key={`${start}-code`}>{match[3]}</code>);
    } else if (match[4]) {
      const citationIndex = Number(match[4]) - 1;
      if (citationIndex >= 0 && citationIndex < citationCount) {
        nodes.push(
          <button
            aria-label={`Open approved source ${citationIndex + 1}`}
            className={styles.sourceReference}
            key={`${start}-source`}
            onClick={(event) => {
              event.stopPropagation();
              onCitationSelect(citationIndex);
            }}
            type="button"
          >
            {citationIndex + 1}
          </button>,
        );
      } else {
        nodes.push(match[0]);
      }
    } else if (match[5]) {
      nodes.push(<em key={`${start}-emphasis`}>{match[5]}</em>);
    }
    cursor = start + match[0].length;
  }

  if (cursor < content.length) nodes.push(content.slice(cursor));
  return nodes;
}

export function FormattedHelpAnswer({
  answer,
  citationCount,
  onCitationSelect,
}: FormattedHelpAnswerProps) {
  return (
    <div className={styles.answerContent}>
      {parseHelpAnswer(answer).map((block, blockIndex) => {
        if (block.type === "heading") {
          return (
            <h4 key={`heading-${blockIndex}`}>
              {inlineContent(block.content, citationCount, onCitationSelect)}
            </h4>
          );
        }
        if (block.type === "ordered-list") {
          return (
            <ol key={`ordered-${blockIndex}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${blockIndex}-${itemIndex}`}>
                  {inlineContent(item, citationCount, onCitationSelect)}
                </li>
              ))}
            </ol>
          );
        }
        if (block.type === "unordered-list") {
          return (
            <ul key={`unordered-${blockIndex}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${blockIndex}-${itemIndex}`}>
                  {inlineContent(item, citationCount, onCitationSelect)}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={`paragraph-${blockIndex}`}>
            {inlineContent(block.content, citationCount, onCitationSelect)}
          </p>
        );
      })}
    </div>
  );
}
