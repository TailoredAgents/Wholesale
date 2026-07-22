"use client";

/* eslint-disable @next/next/no-img-element, react-hooks/set-state-in-effect */

import {
  AlertTriangle,
  Camera,
  Check,
  ClipboardCheck,
  FileSearch,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
  UserRoundCheck,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { ChangeEvent, useCallback, useEffect, useState } from "react";

import type {
  FieldAppointmentWorkspace,
  FieldInspection,
  FieldOperationsOverview,
  FieldRoomObservation,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./field-operations.module.css";
import { useFieldApi } from "./use-field-api";

type MeetingTab = "brief" | "walkthrough" | "negotiation";

type FieldNegotiationLedger = {
  active_plan: {
    id: string;
    opening_offer_cents: number;
    target_contract_cents: number;
    stretch_contract_cents: number;
    seller_ceiling_cents: number;
  } | null;
  concessions: Array<{
    id: string;
    status: string;
    proposed_offer_cents: number;
    seller_exchange: string;
  }>;
  events: Array<{
    event_type: string;
    amount_cents: number | null;
  }>;
};

const repairCategories = [
  "roof", "hvac", "plumbing", "electrical", "foundation", "kitchen", "bathrooms",
  "flooring", "paint_drywall", "windows_doors", "exterior", "landscaping", "permits",
  "cleanup", "other",
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not confirmed";
  return String(value);
}

function money(cents: unknown) {
  if (typeof cents !== "number") return "Not approved";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(cents / 100);
}

function dollars(cents: number | null | undefined) {
  return cents === null || cents === undefined ? "" : String(cents / 100);
}

function cents(value: string) {
  if (!value.trim()) return null;
  return Math.round(Number(value) * 100);
}

async function compressPhoto(file: File): Promise<Blob> {
  if (!file.type.match(/^image\/(jpeg|png|webp)$/) || file.size < 1_200_000) return file;
  const source = URL.createObjectURL(file);
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("This image format could not be prepared."));
      image.src = source;
    });
    const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    canvas.getContext("2d")?.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Photo compression failed."))),
        "image/jpeg",
        0.78,
      ),
    );
  } finally {
    URL.revokeObjectURL(source);
  }
}

function EvidencePhoto({ photo }: { photo: FieldInspection["photos"][number] }) {
  const { fetchBlob } = useFieldApi();
  const [source, setSource] = useState("");
  useEffect(() => {
    let url = "";
    let active = true;
    fetchBlob(photo.content_url)
      .then((blob) => {
        if (!active) return;
        url = URL.createObjectURL(blob);
        setSource(url);
      })
      .catch(() => setSource(""));
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [fetchBlob, photo.content_url]);
  return source ? <img alt={`${photo.area} inspection evidence`} src={source} /> : <Camera size={22} />;
}

export function FieldMeetingWorkspace({
  data,
  requestedAppointmentId,
}: {
  data: FieldOperationsOverview;
  requestedAppointmentId: string;
}) {
  const { request, requestJson, requestPhoto } = useFieldApi();
  const [appointmentId, setAppointmentId] = useState(
    requestedAppointmentId || data.upcoming_appointments[0]?.id || "",
  );
  const [workspace, setWorkspace] = useState<FieldAppointmentWorkspace | null>(null);
  const [tab, setTab] = useState<MeetingTab>("brief");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [inspection, setInspection] = useState<Partial<FieldInspection>>({});
  const [photoArea, setPhotoArea] = useState("Exterior");

  const loadWorkspace = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      setWorkspace(await request<FieldAppointmentWorkspace>(`/api/v1/field-operations/appointments/${id}/workspace`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Meeting workspace unavailable.");
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    if (requestedAppointmentId) setAppointmentId(requestedAppointmentId);
  }, [requestedAppointmentId]);

  useEffect(() => {
    void loadWorkspace(appointmentId);
  }, [appointmentId, loadWorkspace]);

  useEffect(() => {
    setInspection(workspace?.inspection ?? {});
  }, [workspace?.inspection]);

  async function run<T>(operation: () => Promise<T>, success: string) {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await operation();
      setMessage(success);
      await loadWorkspace(appointmentId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The operation could not be completed.");
    } finally {
      setSaving(false);
    }
  }

  function updateInspection<K extends keyof FieldInspection>(key: K, value: FieldInspection[K]) {
    setInspection((current) => ({ ...current, [key]: value }));
  }

  const rooms = inspection.room_observations ?? [];
  const repairs = inspection.repair_items ?? [];
  const brief = workspace?.brief?.brief_data;
  const seller = asRecord(brief?.seller);
  const property = asRecord(brief?.property);
  const underwriting = asRecord(brief?.underwriting);
  const approvedOffer = asRecord(brief?.approved_offer);

  async function saveInspection() {
    if (!workspace?.inspection) return;
    await run(
      () => requestJson(`/api/v1/field-operations/inspections/${workspace.inspection?.id}`, "PATCH", {
        overall_condition: inspection.overall_condition || null,
        occupancy_observed: inspection.occupancy_observed || null,
        utilities_status: inspection.utilities_status || null,
        access_notes: inspection.access_notes || null,
        title_concerns: inspection.title_concerns || null,
        safety_concerns: inspection.safety_concerns || null,
        room_observations: rooms,
        repair_items: repairs,
        inspector_notes: inspection.inspector_notes || null,
      }),
      "Walkthrough draft saved.",
    );
  }

  async function uploadPhotos(event: ChangeEvent<HTMLInputElement>) {
    if (!workspace?.inspection || !event.target.files?.length) return;
    const files = Array.from(event.target.files);
    await run(async () => {
      for (const file of files) {
        const image = await compressPhoto(file);
        const params = new URLSearchParams({ area: photoArea, file_name: file.name });
        await requestPhoto(
          `/api/v1/field-operations/inspections/${workspace.inspection?.id}/photos?${params}`,
          image,
        );
      }
    }, `${files.length} evidence photo${files.length === 1 ? "" : "s"} added.`);
    event.target.value = "";
  }

  return (
    <div className={styles.meetingArea}>
      <section className={styles.fieldScorecards} aria-label="Thirty day closer scorecards">
        {data.scorecards.map((scorecard) => (
          <div key={scorecard.user_id}>
            <span><strong>{scorecard.user_name}</strong><small>Last 30 days</small></span>
            <span><strong>{scorecard.assigned_appointments}</strong><small>Assigned</small></span>
            <span><strong>{Math.round(scorecard.preparation_rate_basis_points / 100)}%</strong><small>Prepared</small></span>
            <span><strong>{Math.round(scorecard.documentation_rate_basis_points / 100)}%</strong><small>Documented</small></span>
            <span><strong>{scorecard.accepted_outcomes}</strong><small>Accepted</small></span>
          </div>
        ))}
      </section>
      <section className={styles.meetingShell}>
      <aside className={styles.meetingQueue}>
        <div className={styles.sectionHeader}>
          <div><span>Assigned field work</span><h3>Seller meetings</h3></div>
          <strong>{data.upcoming_appointments.length}</strong>
        </div>
        <div className={styles.meetingRows}>
          {data.upcoming_appointments.map((appointment) => (
            <button
              className={appointmentId === appointment.id ? styles.selectedMeeting : ""}
              key={appointment.id}
              onClick={() => setAppointmentId(appointment.id)}
              type="button"
            >
              <time>{new Date(appointment.scheduled_start_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</time>
              <span><strong>{appointment.seller_name}</strong><small>{appointment.property_address}</small></span>
            </button>
          ))}
          {!data.upcoming_appointments.length ? <p className={styles.empty}>No assigned seller meetings.</p> : null}
        </div>
      </aside>

      <div className={styles.meetingDesk}>
        {loading ? <div className={styles.workspaceLoading}><LoaderCircle size={20} />Loading meeting…</div> : null}
        {error ? <p className={styles.error}>{error}</p> : null}
        {message ? <p className={styles.notice}>{message}</p> : null}
        {workspace && !loading ? (
          <>
            <header className={styles.meetingHeader}>
              <div>
                <span>{new Date(workspace.appointment.scheduled_start_at).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
                <h3>{workspace.appointment.seller_name}</h3>
                <p>{workspace.appointment.property_address}</p>
              </div>
              <Link href={workspace.appointment.lead_url}>Open lead</Link>
            </header>
            <nav className={styles.meetingTabs} aria-label="Seller meeting workflow">
              <button className={tab === "brief" ? styles.activeMeetingTab : ""} onClick={() => setTab("brief")} type="button"><FileSearch size={16} />Brief</button>
              <button className={tab === "walkthrough" ? styles.activeMeetingTab : ""} onClick={() => setTab("walkthrough")} type="button"><ClipboardCheck size={16} />Walkthrough</button>
              <button className={tab === "negotiation" ? styles.activeMeetingTab : ""} onClick={() => setTab("negotiation")} type="button"><UserRoundCheck size={16} />Outcome</button>
            </nav>

            {tab === "brief" ? (
              <div className={styles.briefWorkspace}>
                <div className={styles.briefActions}>
                  <div><span>Evidence snapshot</span><strong>{workspace.brief ? `Brief v${workspace.brief.version_number}` : "Not generated"}</strong></div>
                  <button disabled={saving} onClick={() => run(
                    () => requestJson(`/api/v1/field-operations/appointments/${appointmentId}/brief`, "POST"),
                    workspace.brief ? "Meeting brief refreshed." : "Meeting brief generated.",
                  )} type="button"><RefreshCw size={16} />{workspace.brief ? "Refresh brief" : "Generate brief"}</button>
                </div>
                {workspace.brief ? (
                  <>
                    <div className={styles.briefFacts}>
                      <div><span>Seller motivation</span><strong>{displayValue(seller.motivation)}</strong></div>
                      <div><span>Desired timeline</span><strong>{displayValue(seller.timeline)}</strong></div>
                      <div><span>Asking price</span><strong>{displayValue(seller.asking_price)}</strong></div>
                      <div><span>Reported condition</span><strong>{displayValue(property.reported_condition)}</strong></div>
                      <div><span>ARV range</span><strong>{money(underwriting.arv_low_cents)} – {money(underwriting.arv_high_cents)}</strong></div>
                      <div><span>Approved ceiling</span><strong>{money(approvedOffer.seller_ceiling_cents)}</strong></div>
                    </div>
                    <div className={styles.briefColumns}>
                      <section><h4>Confirm in person</h4>{asList(brief?.unresolved_questions).map((item, index) => <p key={index}><AlertTriangle size={15} />{String(item)}</p>)}</section>
                      <section><h4>Likely objections</h4>{asList(brief?.likely_objections).map((item, index) => { const objection = asRecord(item); return <p key={index}><span>{labelize(String(objection.category ?? "other"))}</span>{String(objection.reason ?? "Review with seller")}</p>; })}</section>
                      <section><h4>Meeting sequence</h4>{asList(brief?.meeting_plan).map((item, index) => <p key={index}><strong>{index + 1}</strong>{String(item)}</p>)}</section>
                    </div>
                  </>
                ) : <p className={styles.emptyState}>Generate the brief before leaving for the appointment. It freezes the current qualification, underwriting, and approved negotiation evidence into a versioned snapshot.</p>}
              </div>
            ) : null}

            {tab === "walkthrough" ? (
              <div className={styles.walkthroughWorkspace}>
                {!workspace.inspection ? (
                  <button className={styles.primaryAction} disabled={saving} onClick={() => run(
                    () => requestJson(`/api/v1/field-operations/appointments/${appointmentId}/inspection`, "POST"),
                    "Walkthrough started.",
                  )} type="button"><ClipboardCheck size={17} />Start property walkthrough</button>
                ) : (
                  <>
                    <div className={styles.inspectionStatus}><span className={styles.statusPill}>{labelize(workspace.inspection.status)}</span><strong>{money(repairs.reduce((sum, item) => sum + item.estimated_cost_cents, 0))} observed repairs</strong></div>
                    <fieldset className={styles.walkthroughFields} disabled={workspace.inspection.status !== "draft"}>
                      <label><span>Overall condition</span><select onChange={(event) => updateInspection("overall_condition", event.target.value)} value={inspection.overall_condition ?? ""}><option value="">Select condition</option><option value="light">Light repairs</option><option value="moderate">Moderate renovation</option><option value="heavy">Heavy renovation</option><option value="full_renovation">Full renovation</option></select></label>
                      <label><span>Observed occupancy</span><input onChange={(event) => updateInspection("occupancy_observed", event.target.value)} value={inspection.occupancy_observed ?? ""} /></label>
                      <label><span>Utilities</span><input onChange={(event) => updateInspection("utilities_status", event.target.value)} placeholder="On, off, partially on" value={inspection.utilities_status ?? ""} /></label>
                      <label><span>Access notes</span><input onChange={(event) => updateInspection("access_notes", event.target.value)} value={inspection.access_notes ?? ""} /></label>
                      <label><span>Title concerns observed</span><input onChange={(event) => updateInspection("title_concerns", event.target.value)} value={inspection.title_concerns ?? ""} /></label>
                      <label><span>Safety concerns</span><input onChange={(event) => updateInspection("safety_concerns", event.target.value)} value={inspection.safety_concerns ?? ""} /></label>
                    </fieldset>

                    <section className={styles.observationSection}>
                      <header><div><span>Area by area</span><h4>Condition observations</h4></div>{workspace.inspection.status === "draft" ? <button onClick={() => updateInspection("room_observations", [...rooms, { area: "", condition: "fair", notes: null }])} type="button"><Plus size={15} />Add area</button> : null}</header>
                      {rooms.map((room, index) => (
                        <div className={styles.observationRow} key={index}>
                          <input aria-label="Area" disabled={workspace.inspection?.status !== "draft"} onChange={(event) => updateInspection("room_observations", rooms.map((item, itemIndex) => itemIndex === index ? { ...item, area: event.target.value } : item))} placeholder="Kitchen, roof, exterior" value={room.area} />
                          <select aria-label="Condition" disabled={workspace.inspection?.status !== "draft"} onChange={(event) => updateInspection("room_observations", rooms.map((item, itemIndex) => itemIndex === index ? { ...item, condition: event.target.value as FieldRoomObservation["condition"] } : item))} value={room.condition}><option value="good">Good</option><option value="fair">Fair</option><option value="poor">Poor</option><option value="not_inspected">Not inspected</option></select>
                          <input aria-label="Observation notes" disabled={workspace.inspection?.status !== "draft"} onChange={(event) => updateInspection("room_observations", rooms.map((item, itemIndex) => itemIndex === index ? { ...item, notes: event.target.value || null } : item))} placeholder="Observed condition" value={room.notes ?? ""} />
                          {workspace.inspection?.status === "draft" ? <button aria-label="Remove area" onClick={() => updateInspection("room_observations", rooms.filter((_, itemIndex) => itemIndex !== index))} title="Remove area" type="button"><Trash2 size={15} /></button> : null}
                        </div>
                      ))}
                    </section>

                    <section className={styles.observationSection}>
                      <header><div><span>Repair scope</span><h4>Cost observations</h4></div>{workspace.inspection.status === "draft" ? <button onClick={() => updateInspection("repair_items", [...repairs, { category: "other", estimated_cost_cents: 10000, details: null }])} type="button"><Plus size={15} />Add repair</button> : null}</header>
                      {repairs.map((repair, index) => (
                        <div className={styles.repairRow} key={index}>
                          <select disabled={workspace.inspection?.status !== "draft"} onChange={(event) => updateInspection("repair_items", repairs.map((item, itemIndex) => itemIndex === index ? { ...item, category: event.target.value } : item))} value={repair.category}>{repairCategories.map((category) => <option key={category} value={category}>{labelize(category)}</option>)}</select>
                          <label><span>$</span><input disabled={workspace.inspection?.status !== "draft"} min="1" onChange={(event) => updateInspection("repair_items", repairs.map((item, itemIndex) => itemIndex === index ? { ...item, estimated_cost_cents: Math.round(Number(event.target.value) * 100) } : item))} type="number" value={repair.estimated_cost_cents / 100} /></label>
                          <input disabled={workspace.inspection?.status !== "draft"} onChange={(event) => updateInspection("repair_items", repairs.map((item, itemIndex) => itemIndex === index ? { ...item, details: event.target.value || null } : item))} placeholder="Evidence and scope" value={repair.details ?? ""} />
                          {workspace.inspection?.status === "draft" ? <button aria-label="Remove repair" onClick={() => updateInspection("repair_items", repairs.filter((_, itemIndex) => itemIndex !== index))} title="Remove repair" type="button"><Trash2 size={15} /></button> : null}
                        </div>
                      ))}
                    </section>

                    <section className={styles.photoSection}>
                      <header><div><span>Property evidence</span><h4>Photos</h4></div><strong>{workspace.inspection.photos.length}/30</strong></header>
                      {workspace.inspection.status === "draft" ? <div className={styles.photoCapture}><input onChange={(event) => setPhotoArea(event.target.value)} placeholder="Area, such as Kitchen" value={photoArea} /><label><Camera size={17} />Capture or add photos<input accept="image/*" capture="environment" multiple onChange={uploadPhotos} type="file" /></label></div> : null}
                      <div className={styles.photoGrid}>{workspace.inspection.photos.map((photo) => <figure key={photo.id}><EvidencePhoto photo={photo} /><figcaption><strong>{photo.area}</strong><small>{photo.file_name}</small></figcaption>{workspace.inspection?.status === "draft" ? <button aria-label="Delete photo" onClick={() => run(() => requestJson(`/api/v1/field-operations/photos/${photo.id}`, "DELETE"), "Evidence photo removed.")} title="Delete photo" type="button"><Trash2 size={14} /></button> : null}</figure>)}</div>
                    </section>

                    <label className={styles.inspectorNotes}><span>Inspector notes</span><textarea disabled={workspace.inspection.status !== "draft"} onChange={(event) => updateInspection("inspector_notes", event.target.value)} rows={4} value={inspection.inspector_notes ?? ""} /></label>
                    {workspace.inspection.status === "draft" ? <div className={styles.actionRow}><button disabled={saving} onClick={saveInspection} type="button"><Check size={16} />Save draft</button><button className={styles.primaryAction} disabled={saving} onClick={() => run(() => requestJson(`/api/v1/field-operations/inspections/${workspace.inspection?.id}/submit`, "POST"), "Walkthrough submitted for review.")} type="button"><ClipboardCheck size={16} />Submit walkthrough</button></div> : null}
                    {workspace.inspection.status === "submitted" && workspace.can_review_underwriting ? <div className={styles.reviewTransfer}><div><Wrench size={20} /><span><strong>Create reviewed underwriting draft</strong><small>This preserves the old valuation and requires a fresh offer calculation and approval.</small></span></div><button disabled={saving} onClick={() => run(() => requestJson(`/api/v1/field-operations/inspections/${workspace.inspection?.id}/underwriting-transfer`, "POST"), "Field evidence transferred to a new underwriting version.")} type="button">Review and transfer</button></div> : null}
                    {workspace.underwriting_transfer ? <p className={styles.notice}>Transferred to underwriting version {workspace.underwriting_transfer.created_underwriting_version_number}. The prior approved valuation remains unchanged.</p> : null}
                  </>
                )}
              </div>
            ) : null}

            {tab === "negotiation" ? <NegotiationForm appointmentId={appointmentId} saving={saving} workspace={workspace} run={run} /> : null}
          </>
        ) : null}
      </div>
      </section>
    </div>
  );
}

function NegotiationForm({
  appointmentId,
  saving,
  workspace,
  run,
}: {
  appointmentId: string;
  saving: boolean;
  workspace: FieldAppointmentWorkspace;
  run: <T>(operation: () => Promise<T>, success: string) => Promise<void>;
}) {
  const { request, requestJson } = useFieldApi();
  const existing = workspace.negotiation;
  const [decisionMakersConfirmed, setDecisionMakersConfirmed] = useState(existing?.decision_makers_confirmed ?? false);
  const [decisionMakers, setDecisionMakers] = useState(existing?.decision_makers.join(", ") ?? "");
  const [asking, setAsking] = useState(dollars(existing?.seller_asking_price_cents));
  const [presented, setPresented] = useState(dollars(existing?.offer_presented_cents));
  const [counter, setCounter] = useState(dollars(existing?.seller_counter_cents));
  const [agreed, setAgreed] = useState(dollars(existing?.agreed_price_cents));
  const [outcome, setOutcome] = useState(existing?.outcome ?? "pending");
  const [followUp, setFollowUp] = useState(existing?.next_follow_up_at?.slice(0, 16) ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [commitments, setCommitments] = useState(existing?.commitments.join("\n") ?? "");
  const [objections, setObjections] = useState(existing?.objections ?? []);
  const [ledger, setLedger] = useState<FieldNegotiationLedger | null>(null);
  const [concessionAmount, setConcessionAmount] = useState("");
  const [concessionReason, setConcessionReason] = useState("");
  const [sellerExchange, setSellerExchange] = useState("");

  const loadLedger = useCallback(async () => {
    setLedger(
      await request<FieldNegotiationLedger>(
        `/api/v1/leads/${workspace.appointment.lead_id}/underwriting/negotiation-ledger`,
      ),
    );
  }, [request, workspace.appointment.lead_id]);

  useEffect(() => {
    void loadLedger();
  }, [loadLedger]);

  const latestPresented = ledger?.events.find(
    (item) =>
      item.amount_cents !== null &&
      ["concession_presented", "field_offer_presented", "agreement"].includes(item.event_type),
  )?.amount_cents;
  const currentOffer = latestPresented ?? ledger?.active_plan?.opening_offer_cents ?? null;

  async function createConcession() {
    if (!ledger?.active_plan || currentOffer === null) return;
    await run(
      async () => {
        await requestJson(
          `/api/v1/leads/${workspace.appointment.lead_id}/underwriting/concessions`,
          "POST",
          {
            offer_negotiation_plan_id: ledger.active_plan?.id,
            appointment_id: appointmentId,
            previous_offer_cents: currentOffer,
            proposed_offer_cents: cents(concessionAmount),
            seller_counter_cents: cents(counter),
            reason: concessionReason,
            seller_exchange: sellerExchange,
          },
        );
        await loadLedger();
        setConcessionAmount("");
        setConcessionReason("");
        setSellerExchange("");
      },
      "Concession recorded against the approved offer plan.",
    );
  }

  return (
    <form className={styles.negotiationForm} onSubmit={(event) => {
      event.preventDefault();
      void run(() => requestJson(`/api/v1/field-operations/appointments/${appointmentId}/negotiation`, "PUT", {
        decision_makers_confirmed: decisionMakersConfirmed,
        decision_makers: decisionMakers.split(",").map((item) => item.trim()).filter(Boolean),
        seller_asking_price_cents: cents(asking),
        offer_presented_cents: cents(presented),
        seller_counter_cents: cents(counter),
        agreed_price_cents: cents(agreed),
        objections,
        commitments: commitments.split("\n").map((item) => item.trim()).filter(Boolean),
        outcome,
        notes: notes || null,
        next_follow_up_at: followUp ? new Date(followUp).toISOString() : null,
      }), "Seller meeting outcome saved.");
    }}>
      <div className={styles.ceilingBanner}>
        <span>Approved seller ceiling</span>
        <strong>{money(existing?.approved_ceiling_cents ?? ledger?.active_plan?.seller_ceiling_cents ?? asRecord(workspace.brief?.brief_data.approved_offer).seller_ceiling_cents)}</strong>
        <small>The system blocks a presented or agreed price above this approved amount.</small>
      </div>
      {ledger?.active_plan ? (
        <section className={styles.fieldAuthority}>
          <header>
            <div><span>Live offer authority</span><strong>Use a documented step before raising the offer</strong></div>
            <Link href={`/os/leads/${workspace.appointment.lead_id}?tab=underwriting#negotiation-governance`}>Full ledger</Link>
          </header>
          <dl>
            <div><dt>Opening</dt><dd>{money(ledger.active_plan.opening_offer_cents)}</dd></div>
            <div><dt>Current</dt><dd>{money(currentOffer)}</dd></div>
            <div><dt>Target</dt><dd>{money(ledger.active_plan.target_contract_cents)}</dd></div>
            <div><dt>Stretch</dt><dd>{money(ledger.active_plan.stretch_contract_cents)}</dd></div>
            <div><dt>Ceiling</dt><dd>{money(ledger.active_plan.seller_ceiling_cents)}</dd></div>
          </dl>
          <div className={styles.fieldConcessionEditor}>
            <label><span>Next offer</span><input min="0" onChange={(event) => setConcessionAmount(event.target.value)} step="500" type="number" value={concessionAmount} /></label>
            <label><span>Why move?</span><input onChange={(event) => setConcessionReason(event.target.value)} placeholder="Seller evidence or negotiation reason" value={concessionReason} /></label>
            <label><span>Seller exchange</span><input onChange={(event) => setSellerExchange(event.target.value)} placeholder="What Stonegate receives" value={sellerExchange} /></label>
            <button disabled={saving || !concessionAmount || concessionReason.length < 10 || sellerExchange.length < 3} onClick={() => void createConcession()} type="button">Request step</button>
          </div>
          <div className={styles.fieldConcessionChoices}>
            {ledger.concessions.filter((item) => ["authorized", "approved"].includes(item.status)).map((item) => (
              <button key={item.id} onClick={() => setPresented(dollars(item.proposed_offer_cents))} type="button">
                <strong>{money(item.proposed_offer_cents)}</strong>
                <span>{item.status === "approved" ? "Manager approved" : "Pre-authorized"}</span>
              </button>
            ))}
            {ledger.concessions.some((item) => item.status === "pending") ? <p>Manager exception pending. It cannot be presented yet.</p> : null}
          </div>
        </section>
      ) : null}
      <label className={styles.confirmDecisionMakers}><input checked={decisionMakersConfirmed} onChange={(event) => setDecisionMakersConfirmed(event.target.checked)} type="checkbox" /><span><strong>Every decision maker is present or confirmed</strong><small>Required before an accepted agreement can be recorded.</small></span></label>
      <label><span>Decision makers</span><input onChange={(event) => setDecisionMakers(event.target.value)} placeholder="Names, separated by commas" value={decisionMakers} /></label>
      <div className={styles.priceGrid}>
        <label><span>Seller asking</span><input min="0" onChange={(event) => setAsking(event.target.value)} type="number" value={asking} /></label>
        <label><span>Offer presented</span><input min="0" onChange={(event) => setPresented(event.target.value)} type="number" value={presented} /></label>
        <label><span>Seller counter</span><input min="0" onChange={(event) => setCounter(event.target.value)} type="number" value={counter} /></label>
        <label><span>Agreed price</span><input min="0" onChange={(event) => setAgreed(event.target.value)} type="number" value={agreed} /></label>
      </div>
      <section className={styles.objectionEditor}>
        <header><div><span>Negotiation evidence</span><h4>Objections</h4></div><button onClick={() => setObjections((items) => [...items, { category: "price", details: "", response: null, resolved: false }])} type="button"><Plus size={15} />Add objection</button></header>
        {objections.map((objection, index) => <div key={index}><select onChange={(event) => setObjections((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, category: event.target.value } : item))} value={objection.category}>{["price", "timing", "trust", "condition", "family", "title", "competition", "other"].map((item) => <option key={item} value={item}>{labelize(item)}</option>)}</select><input onChange={(event) => setObjections((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, details: event.target.value } : item))} placeholder="What the seller said" value={objection.details} /><input onChange={(event) => setObjections((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, response: event.target.value || null } : item))} placeholder="How it was addressed" value={objection.response ?? ""} /><label><input checked={objection.resolved} onChange={(event) => setObjections((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, resolved: event.target.checked } : item))} type="checkbox" />Resolved</label><button aria-label="Remove objection" onClick={() => setObjections((items) => items.filter((_, itemIndex) => itemIndex !== index))} title="Remove objection" type="button"><Trash2 size={15} /></button></div>)}
      </section>
      <label><span>Seller commitments</span><textarea onChange={(event) => setCommitments(event.target.value)} placeholder="One commitment per line" rows={3} value={commitments} /></label>
      <label><span>Meeting notes</span><textarea onChange={(event) => setNotes(event.target.value)} rows={4} value={notes} /></label>
      <div className={styles.outcomeGrid}>
        <label><span>Outcome</span><select onChange={(event) => setOutcome(event.target.value)} value={outcome}><option value="pending">Meeting in progress</option><option value="follow_up">Follow up</option><option value="not_decided">Not decided</option><option value="accepted">Accepted</option><option value="declined">Declined</option></select></label>
        <label><span>Next follow-up</span><input onChange={(event) => setFollowUp(event.target.value)} type="datetime-local" value={followUp} /></label>
      </div>
      <button className={styles.primaryAction} disabled={saving} type="submit"><Check size={16} />Save outcome</button>
    </form>
  );
}
