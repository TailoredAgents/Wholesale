"use client";

import { useAuth } from "@clerk/nextjs";
import {
  ArrowUp,
  BookOpen,
  ChevronLeft,
  CircleAlert,
  LoaderCircle,
  MessageCircle,
  MessageSquareText,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "../_components/design-system";
import styles from "./help.module.css";

type Citation = {
  document: string;
  title: string;
  heading_path: string;
  excerpt: string;
};

type HelpAnswer = {
  answer: string;
  citations: Citation[];
  used_ai: boolean;
  role_keys: string[];
};

type HelpOverview = {
  title: string;
  description: string;
  suggested_questions: string[];
  available_documents: string[];
  role_keys: string[];
};

type ConversationItem = {
  id: number;
  question: string;
  answer: string;
  citations: Citation[];
  usedAi: boolean;
};

async function errorMessage(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (typeof payload.detail === "string") return payload.detail;
  } catch {
    // The API can fail before producing JSON.
  }
  return `Stonegate Help returned ${response.status}.`;
}

export function HelpBubble({ devUserEmail }: { devUserEmail: string | null }) {
  const { getToken } = useAuth();
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const [overview, setOverview] = useState<HelpOverview | null>(null);
  const [conversation, setConversation] = useState<ConversationItem[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [showSources, setShowSources] = useState(false);

  const headers = useCallback(async (includeJson = false) => {
    const result: Record<string, string> = {};
    const token = await getToken().catch(() => null);
    if (token) result.Authorization = `Bearer ${token}`;
    else if (devUserEmail) result["X-Dev-User-Email"] = devUserEmail;
    if (includeJson) result["Content-Type"] = "application/json";
    return result;
  }, [devUserEmail, getToken]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBase}/api/v1/help`, {
          headers: await headers(),
        });
        if (!response.ok) throw new Error(await errorMessage(response));
        const payload = (await response.json()) as HelpOverview;
        if (!cancelled) setOverview(payload);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Stonegate Help is unavailable.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [apiBase, headers]);

  const selected = conversation.find((item) => item.id === selectedId) ?? conversation.at(-1) ?? null;

  async function ask(event?: FormEvent) {
    event?.preventDefault();
    const cleanQuestion = question.trim();
    if (cleanQuestion.length < 3 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/v1/help/ask`, {
        method: "POST",
        headers: await headers(true),
        body: JSON.stringify({ question: cleanQuestion }),
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const payload = (await response.json()) as HelpAnswer;
      const item: ConversationItem = {
        id: Date.now(),
        question: cleanQuestion,
        answer: payload.answer,
        citations: payload.citations,
        usedAi: payload.used_ai,
      };
      setConversation((current) => [...current, item]);
      setSelectedId(item.id);
      setShowSources(false);
      setQuestion("");
    } catch (askError) {
      setError(askError instanceof Error ? askError.message : "The question could not be answered.");
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask();
    }
  }

  function selectSuggestion(value: string) {
    setQuestion(value);
  }

  function reset() {
    setConversation([]);
    setSelectedId(null);
    setQuestion("");
    setError(null);
    setShowSources(false);
  }

  return (
    <>
      {!open ? (
        <button
          aria-label="Open Stonegate Help"
          className={styles.bubble}
          onClick={() => setOpen(true)}
          type="button"
        >
          <MessageCircle aria-hidden="true" size={25} />
        </button>
      ) : null}
      {open ? (
        <section aria-label="Stonegate Help" aria-modal="false" className={styles.panel} role="dialog">
          <header className={styles.panelHeader}>
            <div>
              <span className={styles.panelMark}><MessageCircle aria-hidden="true" size={18} /></span>
              <div>
                <strong>{showSources ? "Answer sources" : "Stonegate Help"}</strong>
                <small>{showSources ? "Approved documentation" : "Approved guidance"}</small>
              </div>
            </div>
            <div>
              {showSources ? (
                <button aria-label="Back to conversation" onClick={() => setShowSources(false)} type="button">
                  <ChevronLeft aria-hidden="true" size={19} />
                </button>
              ) : null}
              <button aria-label="Close Stonegate Help" onClick={() => setOpen(false)} type="button">
                <X aria-hidden="true" size={19} />
              </button>
            </div>
          </header>
          <div className={styles.workspace}>
      <section
        className={`${styles.conversation} ${showSources ? styles.conversationHidden : ""}`}
        aria-label="Help conversation"
      >
        <header className={styles.conversationHeader}>
          <div>
            <MessageSquareText aria-hidden="true" size={18} />
            <div>
              <strong>Ask Stonegate</strong>
              <span>Approved manuals</span>
            </div>
          </div>
          {conversation.length ? (
            <Button icon={<RotateCcw size={14} />} onClick={reset} size="small" type="button" variant="quiet">
              New conversation
            </Button>
          ) : null}
        </header>

        <div className={styles.messages} aria-live="polite">
          {loading ? (
            <div className={styles.loading}>
              <LoaderCircle aria-hidden="true" size={20} />
              <span>Loading approved manuals…</span>
            </div>
          ) : conversation.length ? (
            conversation.map((item) => (
              <article
                className={item.id === selected?.id ? styles.answerSelected : styles.answer}
                key={item.id}
                onClick={() => setSelectedId(item.id)}
              >
                <div className={styles.question}>
                  <span>You</span>
                  <p>{item.question}</p>
                </div>
                <div className={styles.response}>
                  <span>Stonegate Help</span>
                  {item.answer.split("\n").filter(Boolean).map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                  <button
                    className={styles.citationButton}
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedId(item.id);
                      setShowSources(true);
                    }}
                    type="button"
                  >
                    <BookOpen aria-hidden="true" size={13} />
                    {item.citations.length} approved source{item.citations.length === 1 ? "" : "s"}
                    {item.usedAi ? " · AI summarized" : " · Manual fallback"}
                  </button>
                </div>
              </article>
            ))
          ) : (
            <div className={styles.welcome}>
              <ShieldCheck aria-hidden="true" size={24} />
              <h2>How can I help?</h2>
              <div className={styles.suggestions}>
                {overview?.suggested_questions.map((suggestion) => (
                  <button key={suggestion} onClick={() => selectSuggestion(suggestion)} type="button">
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {error ? (
          <div className={styles.error} role="alert">
            <CircleAlert aria-hidden="true" size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        <form className={styles.composer} onSubmit={ask}>
          <label htmlFor="stonegate-help-question">Question</label>
          <div>
            <textarea
              autoComplete="off"
              disabled={busy || loading}
              id="stonegate-help-question"
              maxLength={500}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask how to use or set up Stonegate…"
              rows={3}
              value={question}
            />
            <button
              aria-label="Ask Stonegate Help"
              disabled={question.trim().length < 3 || busy || loading}
              type="submit"
            >
              {busy ? <LoaderCircle aria-hidden="true" size={17} /> : <ArrowUp aria-hidden="true" size={17} />}
            </button>
          </div>
        </form>
      </section>

      <aside
        className={`${styles.sources} ${showSources ? "" : styles.sourcesHidden}`}
        aria-label="Answer sources"
      >
        <header>
          <div>
            <BookOpen aria-hidden="true" size={17} />
            <strong>Sources</strong>
          </div>
          <span>{selected ? `${selected.citations.length} used` : "Select an answer"}</span>
        </header>
        {selected?.citations.length ? (
          <div className={styles.sourceList}>
            {selected.citations.map((citation, index) => (
              <details key={`${citation.document}-${citation.heading_path}-${index}`} open={index === 0}>
                <summary>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{citation.title}</strong>
                    <small>{citation.heading_path}</small>
                  </div>
                </summary>
                <p>{citation.excerpt}</p>
                <code>{citation.document}</code>
              </details>
            ))}
          </div>
        ) : (
          <div className={styles.sourceEmpty}>
            <BookOpen aria-hidden="true" size={21} />
            <p>Ask a question to see the exact manual sections used.</p>
          </div>
        )}
        <footer>
          <ShieldCheck aria-hidden="true" size={14} />
          <span>{overview?.available_documents.length ?? 0} role-approved documents available</span>
        </footer>
      </aside>
          </div>
        </section>
      ) : null}
    </>
  );
}
