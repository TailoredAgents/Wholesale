"use client";

import {
  ArrowRight,
  Bot,
  ExternalLink,
  LoaderCircle,
  MessageSquareText,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import styles from "./comp-copilot-panel.module.css";

type CopilotCitation = {
  evidence_id: string;
  label: string;
  kind: "analysis" | "subject" | "comparable" | "source";
  comp_key: string | null;
  source_url: string | null;
};

export type CompCopilotAction = {
  action_type:
    | "open_comp_review"
    | "review_comp"
    | "inspect_condition"
    | "verify_micro_market"
    | "refresh_evidence";
  label: string;
  rationale: string;
  comp_key: string | null;
};

type CopilotMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  author_name: string | null;
  citations: CopilotCitation[];
  suggested_actions: CompCopilotAction[];
  confidence: "high" | "medium" | "low" | null;
  limitations: string[];
  used_ai: boolean;
  created_at: string;
};

type CopilotThread = {
  thread_id: string | null;
  analysis_id: string;
  analysis_created_at: string;
  messages: CopilotMessage[];
  suggested_questions: string[];
  ai_available: boolean;
  valuation_authority: "deterministic_v3_only";
};

type CompCopilotPanelProps = {
  analysisId: string;
  apiBaseUrl: string;
  getHeaders: () => Promise<Record<string, string>>;
  leadId: string;
  onSuggestedAction: (action: CompCopilotAction) => void;
};

export function CompCopilotPanel({
  analysisId,
  apiBaseUrl,
  getHeaders,
  leadId,
  onSuggestedAction,
}: CompCopilotPanelProps) {
  const [thread, setThread] = useState<CopilotThread | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const endpoint = `${apiBaseUrl}/api/v1/leads/${leadId}/underwriting/market-analysis/${analysisId}/copilot`;

  const loadThread = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(endpoint, { headers: await getHeaders() });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail ?? "Unable to load the Comp Copilot.");
      }
      setThread(payload as CopilotThread);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load the Comp Copilot.");
    } finally {
      setLoading(false);
    }
  }, [endpoint, getHeaders]);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(endpoint, {
          headers: await getHeaders(),
          signal: controller.signal,
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(payload?.detail ?? "Unable to load the Comp Copilot.");
        }
        setThread(payload as CopilotThread);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught instanceof Error ? caught.message : "Unable to load the Comp Copilot.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [endpoint, getHeaders]);

  useEffect(() => {
    if (thread?.messages.length) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [thread?.messages.length]);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuestion = question.trim();
    if (cleanQuestion.length < 2 || sending) return;
    setSending(true);
    setError(null);
    try {
      const response = await fetch(`${endpoint}/messages`, {
        method: "POST",
        headers: { ...(await getHeaders()), "Content-Type": "application/json" },
        body: JSON.stringify({ question: cleanQuestion }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail ?? "The Comp Copilot could not answer that question.");
      }
      setThread((payload as { thread: CopilotThread }).thread);
      setQuestion("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The Comp Copilot could not answer that question.",
      );
    } finally {
      setSending(false);
    }
  }

  function askSuggested(value: string) {
    setQuestion(value);
  }

  return (
    <section className={styles.panel} aria-labelledby="comp-copilot-title">
      <header className={styles.header}>
        <div className={styles.identity}>
          <span className={styles.icon}>
            <Sparkles aria-hidden="true" size={18} />
          </span>
          <div>
            <span className={styles.eyebrow}>Evidence assistant</span>
            <h3 id="comp-copilot-title">Stonegate Comp Copilot</h3>
            <p>Ask why the evidence looks this way and what a person should verify next.</p>
          </div>
        </div>
        <div className={styles.authority}>
          <ShieldCheck aria-hidden="true" size={15} />
          <span>V3 math remains authoritative</span>
        </div>
      </header>

      {loading ? (
        <div className={styles.loading}>
          <LoaderCircle aria-hidden="true" className={styles.spin} size={19} />
          Loading saved analysis context...
        </div>
      ) : null}

      {!loading && thread ? (
        <>
          <div className={styles.statusStrip}>
            <span data-enabled={thread.ai_available}>
              <Bot aria-hidden="true" size={14} />
              {thread.ai_available ? "AI reasoning available" : "Deterministic guidance mode"}
            </span>
            <small>
              {thread.ai_available
                ? "Answers are grounded only in this saved analysis."
                : "Enable the draft AI Comp Analyst to add conversational reasoning."}
            </small>
          </div>

          {thread.messages.length ? (
            <div className={styles.messages} aria-live="polite">
              {thread.messages.map((message) => (
                <article className={styles.message} data-role={message.role} key={message.id}>
                  <div className={styles.messageMeta}>
                    <strong>
                      {message.role === "assistant" ? "Comp Copilot" : message.author_name ?? "You"}
                    </strong>
                    <span>
                      {message.role === "assistant" && message.used_ai
                        ? "AI draft"
                        : message.role === "assistant"
                          ? "Saved-method guidance"
                          : "Question"}
                    </span>
                  </div>
                  <p>{message.content}</p>
                  {message.citations.length ? (
                    <div className={styles.citations} aria-label="Evidence used">
                      {message.citations.map((citation) =>
                        citation.source_url ? (
                          <a
                            href={citation.source_url}
                            key={citation.evidence_id}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {citation.label}
                            <ExternalLink aria-hidden="true" size={11} />
                          </a>
                        ) : (
                          <span key={citation.evidence_id}>{citation.label}</span>
                        ),
                      )}
                    </div>
                  ) : null}
                  {message.suggested_actions.length ? (
                    <div className={styles.actions}>
                      {message.suggested_actions.map((action, index) => (
                        <button
                          key={`${message.id}-${action.action_type}-${action.comp_key ?? index}`}
                          onClick={() => onSuggestedAction(action)}
                          title={action.rationale}
                          type="button"
                        >
                          {action.label}
                          <ArrowRight aria-hidden="true" size={13} />
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {message.limitations.length ? (
                    <small className={styles.limitation}>{message.limitations.join(" ")}</small>
                  ) : null}
                </article>
              ))}
              <div ref={endRef} />
            </div>
          ) : (
            <div className={styles.empty}>
              <MessageSquareText aria-hidden="true" size={22} />
              <strong>Ask the analysis, not a generic chatbot.</strong>
              <p>
                The Copilot can explain comp selection, confidence, condition gaps, adjustments and
                micro-market review work using the evidence already saved here.
              </p>
            </div>
          )}

          <div className={styles.prompts} aria-label="Suggested Comp Copilot questions">
            {thread.suggested_questions.slice(0, 5).map((suggested) => (
              <button key={suggested} onClick={() => askSuggested(suggested)} type="button">
                {suggested}
              </button>
            ))}
          </div>

          <form className={styles.composer} onSubmit={ask}>
            <label htmlFor={`comp-copilot-question-${analysisId}`}>
              Ask about this saved valuation
            </label>
            <div>
              <textarea
                disabled={sending}
                id={`comp-copilot-question-${analysisId}`}
                maxLength={800}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Why is confidence moderate, and what should I verify next?"
                rows={2}
                value={question}
              />
              <button disabled={sending || question.trim().length < 2} type="submit">
                {sending ? (
                  <LoaderCircle aria-hidden="true" className={styles.spin} size={16} />
                ) : (
                  <Send aria-hidden="true" size={16} />
                )}
                {sending ? "Reviewing..." : "Ask"}
              </button>
            </div>
          </form>
        </>
      ) : null}

      {error ? (
        <div className={styles.error} role="alert">
          <span>{error}</span>
          <button onClick={() => void loadThread()} type="button">
            Try again
          </button>
        </div>
      ) : null}
    </section>
  );
}
