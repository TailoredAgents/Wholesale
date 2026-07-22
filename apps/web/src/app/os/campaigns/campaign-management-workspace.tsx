"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { CampaignManagementOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./campaigns.module.css";

type Tab = "performance" | "import" | "screening" | "costs" | "batches" | "history";
type RequestStatus = "idle" | "saving" | "saved" | "error";
type ImportPreview = {
  headers: string[];
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  suppressed_rows: number;
  review_required_rows: number;
  eligible_rows: number;
  can_import: boolean;
  rows: Array<{
    row_number: number;
    status: string;
    legal_name: string | null;
    phone: string | null;
    property_address: string | null;
    validation_errors: string[];
    eligibility_reasons: string[];
    duplicate_prospect_id: string | null;
  }>;
};
type ImportRequest = {
  campaign_id: string;
  mapping_id: string;
  default_assignee_user_id: string | null;
  file_name: string;
  csv_content: string;
};

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "performance", label: "Performance" },
  { key: "import", label: "Import prospects" },
  { key: "screening", label: "Screening review" },
  { key: "costs", label: "Costs" },
  { key: "batches", label: "Calling batches" },
  { key: "history", label: "Import history" },
];

function value(data: FormData, key: string) {
  return String(data.get(key) ?? "").trim();
}

function dollarsToCents(amount: string) {
  return Math.round(Number(amount || 0) * 100);
}

function formatMoney(cents: number | null) {
  if (cents === null) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function formatPercent(basisPoints: number) {
  return `${(basisPoints / 100).toFixed(1)}%`;
}

function dateLabel(date: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${date}T12:00:00`));
}

export function CampaignManagementWorkspace({ data }: { data: CampaignManagementOverview }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("performance");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [importRequest, setImportRequest] = useState<ImportRequest | null>(null);
  const [selectedImportId, setSelectedImportId] = useState(data.import_batches[0]?.id ?? "");
  const [selectedBatchId, setSelectedBatchId] = useState(data.calling_batches[0]?.id ?? "");
  const [selectedReviewId, setSelectedReviewId] = useState(data.screening_review[0]?.id ?? "");
  const [costCategory, setCostCategory] = useState("list_purchase");
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const activeUsers = data.users.filter((user) => user.is_active);
  const callers = activeUsers.filter((user) =>
    user.role_keys.some((role) => ["prospecting_caller", "acquisition_manager", "administrator"].includes(role)),
  );
  const selectedImport = data.import_batches.find((item) => item.id === selectedImportId);
  const selectedBatch = data.calling_batches.find((item) => item.id === selectedBatchId);
  const selectedReview = data.screening_review.find((item) => item.id === selectedReviewId);
  const totalActualCost = data.quality.reduce((total, campaign) => total + campaign.actual_cost_cents, 0);
  const totalProspects = data.quality.reduce((total, campaign) => total + campaign.imported_prospects, 0);
  const totalCallable = data.quality.reduce((total, campaign) => total + campaign.callable_prospects, 0);
  const totalReview = data.quality.reduce((total, campaign) => total + campaign.review_required_prospects, 0);

  async function request<T>(path: string, method: "POST", body: object): Promise<T | null> {
    setStatus("saving");
    setMessage("");
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = devUserEmail;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers,
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "The operation could not be completed.");
      }
      setStatus("saved");
      setMessage("Saved.");
      return (await response.json()) as T;
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The operation could not be completed.");
      return null;
    }
  }

  async function submitMapping(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const fieldMapping = Object.fromEntries(
      ["source_record_key", "legal_name", "phone", "email", "street_address", "city", "state_code", "postal_code", "dnc_status"]
        .map((key) => [key, value(formData, key)])
        .filter(([, column]) => Boolean(column)),
    );
    const result = await request("/api/v1/campaign-management/import-mappings", "POST", {
      name: value(formData, "name"),
      source_name: value(formData, "source_name") || null,
      field_mapping: fieldMapping,
      default_values: {},
    });
    if (result) {
      form.reset();
      router.refresh();
    }
  }

  async function validateImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const file = formData.get("csv_file");
    if (!(file instanceof File) || !file.size) {
      setStatus("error");
      setMessage("Select a CSV file first.");
      return;
    }
    const payload: ImportRequest = {
      campaign_id: value(formData, "campaign_id"),
      mapping_id: value(formData, "mapping_id"),
      default_assignee_user_id: value(formData, "default_assignee_user_id") || null,
      file_name: file.name,
      csv_content: await file.text(),
    };
    const result = await request<ImportPreview>(
      "/api/v1/campaign-management/imports/validate",
      "POST",
      payload,
    );
    if (result) {
      setPreview(result);
      setImportRequest(payload);
    }
  }

  async function commitImport() {
    if (!importRequest) return;
    const result = await request(
      "/api/v1/campaign-management/imports",
      "POST",
      importRequest,
    );
    if (result) {
      setPreview(null);
      setImportRequest(null);
      router.refresh();
    }
  }

  async function submitCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const isLabor = costCategory === "va_labor";
    const laborHours = Number(value(formData, "labor_hours") || 0);
    const hourlyRate = Number(value(formData, "hourly_rate") || 0);
    const result = await request("/api/v1/campaign-management/costs", "POST", {
      campaign_id: value(formData, "campaign_id"),
      import_batch_id: value(formData, "import_batch_id") || null,
      worker_user_id: isLabor ? value(formData, "worker_user_id") || null : null,
      category: costCategory,
      vendor_name: value(formData, "vendor_name") || null,
      amount_cents: isLabor ? Math.round(laborHours * hourlyRate * 100) : dollarsToCents(value(formData, "amount")),
      labor_minutes: isLabor ? Math.round(laborHours * 60) : null,
      hourly_rate_cents: isLabor ? dollarsToCents(String(hourlyRate)) : null,
      incurred_on: value(formData, "incurred_on"),
      notes: value(formData, "notes") || null,
    });
    if (result) {
      form.reset();
      setCostCategory("list_purchase");
      router.refresh();
    }
  }

  async function submitScreeningDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedReview) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const result = await request(
      `/api/v1/campaign-management/prospects/${selectedReview.id}/screening`,
      "POST",
      {
        dnc_status: value(formData, "dnc_status"),
        source: value(formData, "source"),
        evidence_reference: value(formData, "evidence_reference"),
        notes: value(formData, "notes") || null,
      },
    );
    if (result) {
      form.reset();
      setSelectedReviewId("");
      router.refresh();
    }
  }

  async function submitCallingBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const result = await request("/api/v1/campaign-management/calling-batches", "POST", {
      campaign_id: value(formData, "campaign_id"),
      import_batch_id: value(formData, "import_batch_id") || null,
      assigned_user_id: value(formData, "assigned_user_id"),
      name: value(formData, "name"),
      due_at: value(formData, "due_at") ? new Date(value(formData, "due_at")).toISOString() : null,
      maximum_records: Number(value(formData, "maximum_records")),
      notes: value(formData, "notes") || null,
    });
    if (result) {
      form.reset();
      router.refresh();
    }
  }

  return (
    <section className={styles.workspace}>
      <div className={styles.metrics}>
        <div><span>Imported prospects</span><strong>{totalProspects.toLocaleString()}</strong></div>
        <div><span>Callable now</span><strong>{totalCallable.toLocaleString()}</strong></div>
        <div><span>Needs screening</span><strong>{totalReview.toLocaleString()}</strong></div>
        <div><span>Recorded cost</span><strong>{formatMoney(totalActualCost)}</strong></div>
      </div>

      <div className={styles.tabBar} role="tablist" aria-label="Campaign management views">
        {tabs.map((tab) => (
          <button className={activeTab === tab.key ? styles.activeTab : undefined} key={tab.key} onClick={() => setActiveTab(tab.key)} role="tab" type="button">{tab.label}</button>
        ))}
      </div>
      {status !== "idle" ? <p className={`${styles.feedback} ${styles[status]}`} role="status">{status === "saving" ? "Working..." : message}</p> : null}

      {activeTab === "performance" ? (
        <section className={styles.section}>
          <div className={styles.sectionHeader}><div><span>Campaign economics and data health</span><h3>Performance by campaign</h3></div><strong>{data.quality.length}</strong></div>
          <div className={styles.qualityTable}>
            <div className={styles.tableHeader}><span>Campaign</span><span>Spend</span><span>Data quality</span><span>Callable</span><span>Conversions</span><span>Cost / callable</span><span>Batch progress</span></div>
            {data.quality.map((campaign) => (
              <div className={styles.qualityRow} key={campaign.campaign_id}>
                <div><strong>{campaign.campaign_name}</strong><small>{campaign.imported_prospects.toLocaleString()} imported · {campaign.blocked_prospects} blocked</small></div>
                <div><strong>{formatMoney(campaign.actual_cost_cents)}</strong><small>{campaign.remaining_budget_cents === null ? "No budget" : `${formatMoney(campaign.remaining_budget_cents)} remaining`}</small></div>
                <div><strong>{formatPercent(campaign.bad_data_rate_basis_points)} bad</strong><small>{formatPercent(campaign.duplicate_rate_basis_points)} duplicate</small></div>
                <div><strong>{campaign.callable_prospects.toLocaleString()}</strong><small>{campaign.review_required_prospects} need review</small></div>
                <div><strong>{campaign.converted_prospects}</strong><small>{formatPercent(campaign.conversion_rate_basis_points)}</small></div>
                <div><strong>{formatMoney(campaign.cost_per_callable_prospect_cents)}</strong><small>{formatMoney(campaign.cost_per_imported_prospect_cents)} / imported</small></div>
                <div><strong>{campaign.calling_batch_completed}/{campaign.calling_batch_entries}</strong><div className={styles.progress}><span style={{ width: `${campaign.calling_batch_entries ? campaign.calling_batch_completed / campaign.calling_batch_entries * 100 : 0}%` }} /></div></div>
              </div>
            ))}
            {!data.quality.length ? <p className={styles.empty}>Create a campaign in Acquisition Ops to begin.</p> : null}
          </div>
        </section>
      ) : null}

      {activeTab === "import" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Step 1</span><h3>Reusable vendor mapping</h3></div></div>
            <form className={styles.mappingForm} onSubmit={submitMapping}>
              <label><span>Mapping name</span><input name="name" placeholder="BatchData owner export" required /></label>
              <label><span>Source or vendor</span><input name="source_name" placeholder="Vendor name" /></label>
              <p className={styles.formNote}>Enter each CSV header exactly as it appears in the source file.</p>
              <label><span>Owner name column</span><input defaultValue="Owner" name="legal_name" required /></label>
              <label><span>Phone column</span><input defaultValue="Phone" name="phone" /></label>
              <label><span>Email column</span><input defaultValue="Email" name="email" /></label>
              <label><span>Source ID column</span><input defaultValue="Record ID" name="source_record_key" /></label>
              <label><span>Street column</span><input defaultValue="Property Address" name="street_address" /></label>
              <label><span>City column</span><input defaultValue="City" name="city" /></label>
              <label><span>State column</span><input defaultValue="State" name="state_code" /></label>
              <label><span>ZIP column</span><input defaultValue="ZIP" name="postal_code" /></label>
              <label><span>DNC result column</span><input defaultValue="DNC" name="dnc_status" /></label>
              <button type="submit">Save mapping</button>
            </form>
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Step 2</span><h3>Validate prospect file</h3></div></div>
            <form className={styles.importForm} onSubmit={validateImport}>
              <label><span>Campaign</span><select name="campaign_id" required><option value="">Select campaign</option>{data.campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}</select></label>
              <label><span>Saved mapping</span><select name="mapping_id" required><option value="">Select mapping</option>{data.mappings.map((mapping) => <option key={mapping.id} value={mapping.id}>{mapping.name}</option>)}</select></label>
              <label><span>Default assignee</span><select name="default_assignee_user_id"><option value="">Leave unassigned</option>{callers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
              <label className={styles.fileField}><span>CSV file</span><input accept=".csv,text/csv" name="csv_file" required type="file" /></label>
              <button type="submit">Validate file</button>
            </form>
            {preview ? (
              <div className={styles.preview}>
                <div className={styles.previewMetrics}>
                  <div><span>Rows</span><strong>{preview.total_rows}</strong></div><div><span>Callable</span><strong>{preview.eligible_rows}</strong></div><div><span>Review</span><strong>{preview.review_required_rows}</strong></div><div><span>Blocked</span><strong>{preview.suppressed_rows}</strong></div><div><span>Invalid</span><strong>{preview.invalid_rows}</strong></div><div><span>Duplicates</span><strong>{preview.duplicate_rows}</strong></div>
                </div>
                <div className={styles.previewRows}>
                  {preview.rows.map((row) => <div key={row.row_number}><span>{row.row_number}</span><div><strong>{row.legal_name ?? "Missing owner"}</strong><small>{row.property_address ?? row.phone ?? "No property or phone"}</small></div><span className={`${styles.badge} ${styles[row.status]}`}>{labelize(row.status)}</span><p>{[...row.validation_errors, ...row.eligibility_reasons].join(" ") || "Ready to call after import."}</p></div>)}
                </div>
                <button disabled={!preview.can_import} onClick={commitImport} type="button">Import reviewed file</button>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}

      {activeTab === "costs" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Actual spend</span><h3>Campaign cost ledger</h3></div><strong>{data.costs.length}</strong></div>
            <div className={styles.rows}>{data.costs.map((cost) => <div className={styles.costRow} key={cost.id}><div><strong>{cost.campaign_name}</strong><span>{labelize(cost.category)}{cost.worker_name ? ` · ${cost.worker_name}` : ""}</span></div><div><strong>{formatMoney(cost.amount_cents)}</strong><span>{dateLabel(cost.incurred_on)}</span></div></div>)}{!data.costs.length ? <p className={styles.empty}>No campaign costs recorded.</p> : null}</div>
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Attribution</span><h3>Record a cost</h3></div></div>
            <form className={styles.stackForm} onSubmit={submitCost}>
              <label><span>Campaign</span><select name="campaign_id" required><option value="">Select campaign</option>{data.campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}</select></label>
              <label><span>Category</span><select name="category" onChange={(event) => setCostCategory(event.target.value)} value={costCategory}><option value="list_purchase">List purchase</option><option value="va_labor">VA labor</option><option value="data_enrichment">Data enrichment</option><option value="direct_mail">Direct mail</option><option value="ad_spend">Ad spend</option><option value="software">Software</option><option value="other">Other</option></select></label>
              <label><span>Related import</span><select name="import_batch_id"><option value="">No import</option>{data.import_batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.file_name}</option>)}</select></label>
              <label><span>Incurred on</span><input defaultValue={new Date().toISOString().slice(0, 10)} name="incurred_on" required type="date" /></label>
              {costCategory === "va_labor" ? <><label><span>Worker</span><select name="worker_user_id" required><option value="">Select worker</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label><label><span>Hours</span><input min="0.01" name="labor_hours" required step="0.01" type="number" /></label><label><span>Hourly rate ($)</span><input defaultValue="7" min="0" name="hourly_rate" required step="0.01" type="number" /></label></> : <label><span>Amount ($)</span><input min="0" name="amount" required step="0.01" type="number" /></label>}
              <label><span>Vendor</span><input name="vendor_name" /></label>
              <label className={styles.full}><span>Notes</span><textarea name="notes" rows={3} /></label>
              <button type="submit">Record cost</button>
            </form>
          </section>
        </div>
      ) : null}

      {activeTab === "screening" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Not callable until reviewed</span><h3>Screening queue</h3></div><strong>{data.screening_review.length}</strong></div>
            <div className={styles.picker}>{data.screening_review.map((prospect) => <button className={selectedReviewId === prospect.id ? styles.selected : undefined} key={prospect.id} onClick={() => setSelectedReviewId(prospect.id)} type="button"><strong>{prospect.legal_name}</strong><span>{prospect.campaign_name} · {prospect.phone ?? "No phone"}</span></button>)}{!data.screening_review.length ? <p className={styles.empty}>No prospects are awaiting screening.</p> : null}</div>
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>{selectedReview?.campaign_name ?? "Select a prospect"}</span><h3>{selectedReview?.legal_name ?? "Screening evidence"}</h3></div></div>
            {selectedReview ? <form className={styles.stackForm} onSubmit={submitScreeningDecision}>
              <p className={styles.formNote}>{selectedReview.property_address ?? selectedReview.phone ?? "No contact details"}</p>
              <label><span>DNC result</span><select name="dnc_status" required><option value="clear">Clear</option><option value="blocked">Blocked</option></select></label>
              <label><span>Screening source</span><input name="source" placeholder="Provider or compliance reviewer" required /></label>
              <label className={styles.full}><span>Evidence reference</span><input name="evidence_reference" placeholder="Report ID, export name, or retained file reference" required /></label>
              <label className={styles.full}><span>Review notes</span><textarea name="notes" rows={4} /></label>
              <button type="submit">Record screening decision</button>
            </form> : <p className={styles.empty}>Select a prospect to record retained screening evidence.</p>}
          </section>
        </div>
      ) : null}

      {activeTab === "batches" ? (
        <div className={styles.twoColumn}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Controlled assignments</span><h3>Prospect calling batches</h3></div><strong>{data.calling_batches.length}</strong></div>
            <div className={styles.picker}>{data.calling_batches.map((batch) => <button className={selectedBatchId === batch.id ? styles.selected : undefined} key={batch.id} onClick={() => setSelectedBatchId(batch.id)} type="button"><strong>{batch.name}</strong><span>{batch.assigned_user_name} · {batch.completed_entries}/{batch.total_entries}</span></button>)}</div>
            <form className={styles.stackForm} onSubmit={submitCallingBatch}>
              <label><span>Batch name</span><input name="name" required /></label>
              <label><span>Campaign</span><select name="campaign_id" required><option value="">Select campaign</option>{data.campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}</select></label>
              <label><span>Import batch</span><select name="import_batch_id"><option value="">Any unbatched campaign records</option>{data.import_batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.file_name}</option>)}</select></label>
              <label><span>Assigned caller</span><select name="assigned_user_id" required><option value="">Select caller</option>{callers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
              <label><span>Maximum records</span><input defaultValue="100" max="1000" min="1" name="maximum_records" type="number" /></label>
              <label><span>Due by</span><input name="due_at" type="datetime-local" /></label>
              <label className={styles.full}><span>Notes</span><textarea name="notes" rows={3} /></label>
              <button type="submit">Create callable batch</button>
            </form>
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>{selectedBatch?.assigned_user_name ?? "No caller selected"}</span><h3>{selectedBatch?.name ?? "Batch records"}</h3></div>{selectedBatch ? <strong>{selectedBatch.total_entries}</strong> : null}</div>
            <div className={styles.batchEntries}>{selectedBatch?.entries.map((entry) => <div key={entry.id}><span>{entry.sequence_number}</span><div><strong>{entry.legal_name}</strong><small>{entry.property_address ?? entry.phone ?? "No address"}</small></div><span className={styles.badge}>{labelize(entry.status)}</span></div>)}{!selectedBatch ? <p className={styles.empty}>Select or create a calling batch.</p> : null}</div>
          </section>
        </div>
      ) : null}

      {activeTab === "history" ? (
        <div className={styles.historyLayout}>
          <section className={styles.section}><div className={styles.sectionHeader}><div><span>Import lineage</span><h3>Committed files</h3></div></div><div className={styles.picker}>{data.import_batches.map((batch) => <button className={selectedImportId === batch.id ? styles.selected : undefined} key={batch.id} onClick={() => setSelectedImportId(batch.id)} type="button"><strong>{batch.file_name}</strong><span>{batch.campaign_name} · {batch.imported_rows}/{batch.total_rows} imported</span></button>)}{!data.import_batches.length ? <p className={styles.empty}>No files imported.</p> : null}</div></section>
          <section className={styles.section}><div className={styles.sectionHeader}><div><span>{selectedImport?.mapping_name ?? "No import selected"}</span><h3>{selectedImport?.file_name ?? "Row-level results"}</h3></div>{selectedImport ? <strong>{selectedImport.total_rows}</strong> : null}</div><div className={styles.historyRows}>{selectedImport?.rows.map((row) => <div key={row.id}><span>{row.row_number}</span><div><strong>{row.legal_name ?? "Missing owner"}</strong><small>{row.property_address ?? row.phone ?? "No address or phone"}</small></div><span className={`${styles.badge} ${styles[row.status.replace("imported_", "")]}`}>{labelize(row.status)}</span><p>{[...row.validation_errors, ...row.eligibility_reasons].join(" ") || "Imported with clear screening evidence."}</p></div>)}{!selectedImport ? <p className={styles.empty}>Select an import to inspect every row.</p> : null}</div></section>
        </div>
      ) : null}
    </section>
  );
}
