"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Archive,
  CheckCircle2,
  Edit3,
  Plus,
  RotateCcw,
  Save,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { TrustProofOverview, TrustProofRecord } from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./trust-proof-workspace.module.css";

type RequestStatus = "idle" | "saving" | "saved" | "error";

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function nullable(data: FormData, key: string) {
  return value(data, key) || null;
}

function tone(status: string) {
  if (status === "published" || status === "granted") return "success";
  if (status === "retired" || status === "revoked") return "danger";
  if (status === "in_review" || status === "pending") return "warning";
  return "neutral";
}

function recordPayload(data: FormData) {
  const rating = value(data, "rating");
  return {
    proof_type: value(data, "proof_type"),
    title: value(data, "title"),
    content: nullable(data, "content"),
    attribution_name: nullable(data, "attribution_name"),
    attribution_detail: nullable(data, "attribution_detail"),
    location_label: nullable(data, "location_label"),
    rating: rating ? Number(rating) : null,
    metric_label: nullable(data, "metric_label"),
    metric_value: nullable(data, "metric_value"),
    methodology: nullable(data, "methodology"),
    as_of_date: nullable(data, "as_of_date"),
    source_type: value(data, "source_type"),
    source_url: nullable(data, "source_url"),
    source_reference: nullable(data, "source_reference"),
    show_source_link: data.get("show_source_link") === "on",
    permission_status: value(data, "permission_status"),
    permission_evidence_notes: nullable(data, "permission_evidence_notes"),
    material_connection: nullable(data, "material_connection"),
    disclosure: nullable(data, "disclosure"),
    featured: data.get("featured") === "on",
    sort_order: Number(value(data, "sort_order") || 0),
  };
}

export function TrustProofWorkspace({
  initialData,
  apiConnected,
}: {
  initialData: TrustProofOverview;
  apiConnected: boolean;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const selected = initialData.records.find((record) => record.id === editingId) ?? null;
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );

  async function headers() {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }

  async function mutate(path: string, method: "POST" | "PATCH", body: object) {
    setStatus("saving");
    setMessage("");
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: await headers(),
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail ?? "The proof operation could not be completed.");
      }
      setStatus("saved");
      setMessage("Saved. Public content refreshes within five minutes after publication.");
      router.refresh();
      return true;
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof Error ? error.message : "The proof operation could not be completed.",
      );
      return false;
    }
  }

  async function saveRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = recordPayload(new FormData(form));
    const saved = await mutate(
      selected
        ? `/api/v1/marketing/trust-proofs/${selected.id}`
        : "/api/v1/marketing/trust-proofs",
      selected ? "PATCH" : "POST",
      payload,
    );
    if (saved && !selected) {
      form.reset();
    }
  }

  async function decide(
    record: TrustProofRecord,
    decision: "submit_review" | "publish" | "return_to_draft" | "retire",
  ) {
    const reason = window.prompt(`Document why this proof should be ${labelize(decision)}.`);
    if (!reason) return;
    await mutate(`/api/v1/marketing/trust-proofs/${record.id}/decision`, "POST", {
      decision,
      reason,
    });
  }

  const counts = initialData.records.reduce<Record<string, number>>((result, record) => {
    result[record.publication_status] = (result[record.publication_status] ?? 0) + 1;
    return result;
  }, {});

  return (
    <section className={styles.workspace} aria-labelledby="public-proof-title">
      <div className={styles.heading}>
        <div>
          <span>Public trust governance</span>
          <h2 id="public-proof-title">Reviews, seller stories, and verified outcomes</h2>
          <p>
            Nothing appears on the public site until its source, usage permission, and publication
            decision are documented.
          </p>
        </div>
        <div className={styles.summary} aria-label="Public proof status">
          <span><strong>{counts.published ?? 0}</strong> Published</span>
          <span><strong>{counts.in_review ?? 0}</strong> In review</span>
          <span><strong>{counts.draft ?? 0}</strong> Drafts</span>
        </div>
      </div>

      {!apiConnected ? (
        <p className={styles.error} role="status">Public proof data is currently unavailable.</p>
      ) : null}
      {status !== "idle" ? (
        <p className={styles[status]} role="status">
          {status === "saving" ? "Saving..." : message}
        </p>
      ) : null}

      <div className={styles.library}>
        <div className={styles.recordList}>
          <div className={styles.listHeader}>
            <strong>Proof library</strong>
            {initialData.can_manage ? (
              <button type="button" onClick={() => setEditingId(null)}>
                <Plus size={15} aria-hidden="true" />
                New proof
              </button>
            ) : null}
          </div>
          {initialData.records.length ? (
            initialData.records.map((record) => (
              <article key={record.id}>
                <button
                  className={editingId === record.id ? styles.selectedRecord : undefined}
                  type="button"
                  onClick={() => setEditingId(record.id)}
                >
                  <span>
                    <small>{labelize(record.proof_type)}</small>
                    <strong>{record.title}</strong>
                  </span>
                  <Edit3 size={15} aria-hidden="true" />
                </button>
                <div>
                  <StatusBadge tone={tone(record.publication_status)}>
                    {labelize(record.publication_status)}
                  </StatusBadge>
                  <StatusBadge tone={tone(record.permission_status)}>
                    {labelize(record.permission_status)}
                  </StatusBadge>
                </div>
              </article>
            ))
          ) : (
            <p className={styles.empty}>
              No public proof exists. Empty proof sections remain completely hidden from sellers.
            </p>
          )}
        </div>

        {initialData.can_manage ? (
          <form
            className={styles.editor}
            key={selected?.id ?? "new-proof"}
            onSubmit={saveRecord}
          >
            <div className={styles.editorHeader}>
              <div>
                <span>{selected ? "Proof record" : "New proof"}</span>
                <h3>{selected?.title ?? "Prepare evidence-backed content"}</h3>
              </div>
              {selected ? (
                <StatusBadge tone={tone(selected.publication_status)}>
                  {labelize(selected.publication_status)}
                </StatusBadge>
              ) : null}
            </div>

            <fieldset disabled={Boolean(selected && selected.publication_status !== "draft")}>
              <legend>Public content</legend>
              <div className={styles.formGrid}>
                <label>
                  Proof type
                  <select name="proof_type" defaultValue={selected?.proof_type ?? "review"}>
                    <option value="review">Review</option>
                    <option value="seller_story">Seller story</option>
                    <option value="completed_purchase">Completed purchase</option>
                    <option value="statistic">Statistic</option>
                  </select>
                </label>
                <label>
                  Public title
                  <input name="title" required defaultValue={selected?.title ?? ""} />
                </label>
                <label className={styles.full}>
                  Approved public text
                  <textarea name="content" rows={4} defaultValue={selected?.content ?? ""} />
                </label>
                <label>
                  Public attribution
                  <input
                    name="attribution_name"
                    defaultValue={selected?.attribution_name ?? ""}
                    placeholder="Approved name or initials"
                  />
                </label>
                <label>
                  Attribution detail
                  <input
                    name="attribution_detail"
                    defaultValue={selected?.attribution_detail ?? ""}
                    placeholder="Georgia property seller"
                  />
                </label>
                <label>
                  Public location
                  <input
                    name="location_label"
                    defaultValue={selected?.location_label ?? ""}
                    placeholder="Canton, Georgia"
                  />
                </label>
                <label>
                  User-provided rating
                  <select name="rating" defaultValue={selected?.rating ?? ""}>
                    <option value="">No rating</option>
                    {[1, 2, 3, 4, 5].map((rating) => (
                      <option value={rating} key={rating}>{rating}</option>
                    ))}
                  </select>
                </label>
              </div>
            </fieldset>

            <fieldset disabled={Boolean(selected && selected.publication_status !== "draft")}>
              <legend>Verified outcome fields</legend>
              <div className={styles.formGrid}>
                <label>
                  Metric label
                  <input name="metric_label" defaultValue={selected?.metric_label ?? ""} />
                </label>
                <label>
                  Metric value
                  <input name="metric_value" defaultValue={selected?.metric_value ?? ""} />
                </label>
                <label>
                  As-of or completion date
                  <input name="as_of_date" type="date" defaultValue={selected?.as_of_date ?? ""} />
                </label>
                <label>
                  Sort order
                  <input
                    name="sort_order"
                    type="number"
                    min="-1000"
                    max="1000"
                    defaultValue={selected?.sort_order ?? 0}
                  />
                </label>
                <label className={styles.full}>
                  Calculation method
                  <textarea
                    name="methodology"
                    rows={3}
                    defaultValue={selected?.methodology ?? ""}
                    placeholder="Required for statistics; explain records, date range, and calculation."
                  />
                </label>
              </div>
            </fieldset>

            <fieldset disabled={Boolean(selected && selected.publication_status !== "draft")}>
              <legend>Source, permission, and disclosure</legend>
              <div className={styles.formGrid}>
                <label>
                  Source type
                  <select name="source_type" defaultValue={selected?.source_type ?? "google_review"}>
                    <option value="google_review">Google review</option>
                    <option value="seller_permission">Seller permission</option>
                    <option value="signed_release">Signed release</option>
                    <option value="transaction_record">Transaction record</option>
                    <option value="accounting_record">Accounting record</option>
                    <option value="other">Other evidence</option>
                  </select>
                </label>
                <label>
                  Permission status
                  <select
                    name="permission_status"
                    defaultValue={selected?.permission_status ?? "pending"}
                  >
                    <option value="pending">Pending</option>
                    <option value="granted">Granted</option>
                    <option value="not_required">Not required</option>
                    <option value="revoked">Revoked</option>
                  </select>
                </label>
                <label className={styles.full}>
                  Source URL
                  <input
                    name="source_url"
                    type="url"
                    defaultValue={selected?.source_url ?? ""}
                    placeholder="https://..."
                  />
                </label>
                <label className={styles.full}>
                  Internal evidence reference
                  <input
                    name="source_reference"
                    defaultValue={selected?.source_reference ?? ""}
                    placeholder="Transaction ID, signed release, or evidence location"
                  />
                </label>
                <label className={styles.full}>
                  Permission evidence
                  <textarea
                    name="permission_evidence_notes"
                    rows={3}
                    defaultValue={selected?.permission_evidence_notes ?? ""}
                    placeholder="Where consent is recorded, or why permission is not required."
                  />
                </label>
                <label>
                  Material connection
                  <input
                    name="material_connection"
                    defaultValue={selected?.material_connection ?? ""}
                    placeholder="Employee, family, incentive, or other connection"
                  />
                </label>
                <label>
                  Visible disclosure
                  <input
                    name="disclosure"
                    defaultValue={selected?.disclosure ?? ""}
                    placeholder="Required when a material connection exists"
                  />
                </label>
              </div>
              <div className={styles.checks}>
                <label>
                  <input
                    name="show_source_link"
                    type="checkbox"
                    defaultChecked={selected?.show_source_link ?? false}
                  />
                  Show approved source link publicly
                </label>
                <label>
                  <input
                    name="featured"
                    type="checkbox"
                    defaultChecked={selected?.featured ?? false}
                  />
                  Feature before other proof
                </label>
              </div>
            </fieldset>

            <div className={styles.actions}>
              {(!selected || selected.publication_status === "draft") ? (
                <button className={styles.primaryAction} type="submit">
                  <Save size={16} aria-hidden="true" />
                  {selected ? "Save draft" : "Create draft"}
                </button>
              ) : null}
              {selected?.publication_status === "draft" ? (
                <button type="button" onClick={() => decide(selected, "submit_review")}>
                  <Send size={16} aria-hidden="true" />
                  Submit for review
                </button>
              ) : null}
              {selected?.publication_status === "in_review" ? (
                <>
                  <button
                    className={styles.primaryAction}
                    type="button"
                    onClick={() => decide(selected, "publish")}
                  >
                    <CheckCircle2 size={16} aria-hidden="true" />
                    Publish
                  </button>
                  <button type="button" onClick={() => decide(selected, "return_to_draft")}>
                    <RotateCcw size={16} aria-hidden="true" />
                    Return to draft
                  </button>
                </>
              ) : null}
              {selected?.publication_status === "published" ? (
                <>
                  <button type="button" onClick={() => decide(selected, "return_to_draft")}>
                    <RotateCcw size={16} aria-hidden="true" />
                    Unpublish and edit
                  </button>
                  <button type="button" onClick={() => decide(selected, "retire")}>
                    <Archive size={16} aria-hidden="true" />
                    Retire
                  </button>
                </>
              ) : null}
              {selected?.publication_status === "retired" ? (
                <button type="button" onClick={() => decide(selected, "return_to_draft")}>
                  <RotateCcw size={16} aria-hidden="true" />
                  Restore as draft
                </button>
              ) : null}
            </div>
          </form>
        ) : (
          <div className={styles.readOnly}>
            <ShieldCheck size={24} aria-hidden="true" />
            <h3>Reporting access only</h3>
            <p>Only Owner and authorized Marketing roles can change public proof.</p>
          </div>
        )}
      </div>
    </section>
  );
}
