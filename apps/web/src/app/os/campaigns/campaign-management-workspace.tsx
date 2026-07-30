"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { CampaignManagementOverview } from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./campaigns.module.css";

type Tab = "performance" | "import" | "costs" | "batches" | "history";
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
    relationship_state: string;
    contact_point_count: number;
  }>;
};
type ImportRequest = {
  campaign_id: string;
  mapping_id: string;
  cohort_id: string | null;
  default_assignee_user_id: string | null;
  file_name: string;
  csv_content: string;
  source_profile: "general_csv" | "propstream";
  source_export_id: string | null;
  source_list_id: string | null;
  source_list_name: string | null;
  source_exported_at: string | null;
  source_filters: Record<string, string>;
};

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "performance", label: "Performance" },
  { key: "import", label: "Import prospects" },
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

function callingModeLabel() {
  return "One-by-one calling";
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
  const [costCategory, setCostCategory] = useState("list_purchase");
  const [sourceProfile, setSourceProfile] = useState<"general_csv" | "propstream">("propstream");
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
      ["source_record_key", "legal_name", "legal_first_name", "legal_last_name", "phone", "phone_2", "phone_3", "email", "email_2", "email_3", "street_address", "city", "state_code", "postal_code", "dnc_status"]
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

  async function addPropStreamPreset() {
    const result = await request(
      "/api/v1/campaign-management/import-mappings/propstream-preset",
      "POST",
      {},
    );
    if (result) router.refresh();
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
    const sourceFilters = Object.fromEntries(
      ["market", "county", "distress_signal", "minimum_equity_percent", "ownership_years", "occupancy", "property_type"]
        .map((key) => [key, value(formData, key)])
        .filter(([, filterValue]) => Boolean(filterValue)),
    );
    const exportedAt = value(formData, "source_exported_at");
    const payload: ImportRequest = {
      campaign_id: value(formData, "campaign_id"),
      mapping_id: value(formData, "mapping_id"),
      cohort_id: value(formData, "cohort_id") || null,
      default_assignee_user_id: value(formData, "default_assignee_user_id") || null,
      file_name: file.name,
      csv_content: await file.text(),
      source_profile: sourceProfile,
      source_export_id: value(formData, "source_export_id") || null,
      source_list_id: value(formData, "source_list_id") || null,
      source_list_name: value(formData, "source_list_name") || null,
      source_exported_at: exportedAt ? new Date(exportedAt).toISOString() : null,
      source_filters: sourceFilters,
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
      cohort_id: value(formData, "cohort_id") || null,
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

  async function submitCallingBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const cohortId = value(formData, "cohort_id");
    const cohort = data.cohorts.find((item) => item.id === cohortId);
    const result = await request("/api/v1/campaign-management/calling-batches", "POST", {
      campaign_id: value(formData, "campaign_id"),
      import_batch_id: value(formData, "import_batch_id") || null,
      cohort_id: cohortId || null,
      dialer_mode: cohort?.dialer_mode ?? "one_line_power",
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
        <div><span>Needs phone data</span><strong>{totalReview.toLocaleString()}</strong></div>
        <div><span>Recorded cost</span><strong>{formatMoney(totalActualCost)}</strong></div>
      </div>

      <div className={styles.tabBar} role="tablist" aria-label="Campaign management views">
        {tabs.map((tab) => (
          <button className={activeTab === tab.key ? styles.activeTab : undefined} key={tab.key} onClick={() => setActiveTab(tab.key)} role="tab" type="button">{tab.label}</button>
        ))}
      </div>
      {status !== "idle" ? <p className={`${styles.feedback} ${styles[status]}`} role="status">{status === "saving" ? "Working..." : message}</p> : null}

      {activeTab === "performance" ? (
        <section
          aria-label="Campaign performance table"
          className={styles.section}
          tabIndex={0}
        >
          <div className={styles.sectionHeader}><div><span>Campaign economics and data health</span><h3>Performance by campaign</h3></div><strong>{data.quality.length}</strong></div>
          <div className={styles.qualityTable}>
            <div className={styles.tableHeader}><span>Campaign</span><span>Spend</span><span>Data quality</span><span>Callable</span><span>Warm leads</span><span>Cost / warm lead</span><span>Batch progress</span></div>
            {data.quality.map((campaign) => (
              <div className={styles.qualityRow} key={campaign.campaign_id}>
                <div><strong>{campaign.campaign_name}</strong><small>{campaign.imported_prospects.toLocaleString()} imported · {campaign.blocked_prospects} blocked</small></div>
                <div><strong>{formatMoney(campaign.actual_cost_cents)}</strong><small>{campaign.remaining_budget_cents === null ? "No budget" : `${formatMoney(campaign.remaining_budget_cents)} remaining`}</small></div>
                <div><strong>{formatPercent(campaign.bad_data_rate_basis_points)} bad</strong><small>{formatPercent(campaign.duplicate_rate_basis_points)} duplicate</small></div>
                <div><strong>{campaign.callable_prospects.toLocaleString()}</strong><small>{campaign.review_required_prospects} need review</small></div>
                <div><strong>{campaign.accepted_warm_leads}</strong><small>{campaign.submitted_handoffs} submitted · {campaign.rejected_handoffs} rejected</small></div>
                <div><strong>{formatMoney(campaign.cost_per_accepted_warm_lead_cents)}</strong><small>{formatMoney(campaign.cost_per_callable_prospect_cents)} / callable</small></div>
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
            <div className={styles.sectionHeader}><div><span>Step 1</span><h3>Reusable vendor mapping</h3></div><button onClick={addPropStreamPreset} type="button">Add PropStream preset</button></div>
            <form className={styles.mappingForm} onSubmit={submitMapping}>
              <label><span>Mapping name</span><input name="name" placeholder="BatchData owner export" required /></label>
              <label><span>Source or vendor</span><input name="source_name" placeholder="Vendor name" /></label>
              <p className={styles.formNote}>Enter each CSV header exactly as it appears in the source file.</p>
              <label><span>Owner name column</span><input defaultValue="Owner" name="legal_name" required /></label>
              <label><span>Phone column</span><input defaultValue="Phone" name="phone" /></label>
              <label><span>Phone 2 column</span><input name="phone_2" /></label>
              <label><span>Phone 3 column</span><input name="phone_3" /></label>
              <label><span>Email column</span><input defaultValue="Email" name="email" /></label>
              <label><span>Email 2 column</span><input name="email_2" /></label>
              <label><span>Email 3 column</span><input name="email_3" /></label>
              <label><span>Source ID column</span><input defaultValue="Record ID" name="source_record_key" /></label>
              <label><span>Street column</span><input defaultValue="Property Address" name="street_address" /></label>
              <label><span>City column</span><input defaultValue="City" name="city" /></label>
              <label><span>State column</span><input defaultValue="State" name="state_code" /></label>
              <label><span>ZIP column</span><input defaultValue="ZIP" name="postal_code" /></label>
              <label><span>Do-not-call flag column (optional)</span><input defaultValue="DNC" name="dnc_status" /></label>
              <button type="submit">Save mapping</button>
            </form>
          </section>
          <section className={styles.section}>
            <div className={styles.sectionHeader}><div><span>Step 2</span><h3>Validate prospect file</h3></div></div>
            <form className={styles.importForm} onSubmit={validateImport}>
              <label><span>Campaign</span><select name="campaign_id" required><option value="">Select campaign</option>{data.campaigns.map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}</select></label>
              <label><span>Saved mapping</span><select name="mapping_id" required><option value="">Select mapping</option>{data.mappings.map((mapping) => <option key={mapping.id} value={mapping.id}>{mapping.name}</option>)}</select></label>
              <label><span>Source format</span><select onChange={(event) => setSourceProfile(event.target.value as "general_csv" | "propstream")} value={sourceProfile}><option value="propstream">PropStream export</option><option value="general_csv">General CSV</option></select></label>
              <label><span>Measurement cohort</span><select name="cohort_id"><option value="">No cohort</option>{data.cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name} · {callingModeLabel()}</option>)}</select></label>
              <label><span>Default assignee</span><select name="default_assignee_user_id"><option value="">Leave unassigned</option>{callers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>
              <label><span>PropStream export ID</span><input name="source_export_id" /></label>
              <label><span>Saved list ID</span><input name="source_list_id" /></label>
              <label><span>Saved list name</span><input name="source_list_name" placeholder="Atlanta absentee high equity" /></label>
              <label><span>Exported at</span><input name="source_exported_at" type="datetime-local" /></label>
              <label><span>Market</span><input name="market" placeholder="Atlanta Metro" /></label>
              <label><span>County</span><input name="county" placeholder="Fulton" /></label>
              <label><span>Distress signal</span><input name="distress_signal" placeholder="Absentee, vacant, pre-foreclosure" /></label>
              <label><span>Minimum equity %</span><input max="100" min="0" name="minimum_equity_percent" type="number" /></label>
              <label><span>Ownership years</span><input min="0" name="ownership_years" type="number" /></label>
              <label><span>Occupancy</span><input name="occupancy" placeholder="Absentee" /></label>
              <label><span>Property type</span><input name="property_type" placeholder="Single family" /></label>
              <label className={styles.fileField}><span>CSV file</span><input accept=".csv,text/csv" name="csv_file" required type="file" /></label>
              <button type="submit">Validate file</button>
            </form>
            {preview ? (
              <div className={styles.preview}>
                <div className={styles.previewMetrics}>
                  <div><span>Rows</span><strong>{preview.total_rows}</strong></div><div><span>Callable</span><strong>{preview.eligible_rows}</strong></div><div><span>Review</span><strong>{preview.review_required_rows}</strong></div><div><span>Blocked</span><strong>{preview.suppressed_rows}</strong></div><div><span>Invalid</span><strong>{preview.invalid_rows}</strong></div><div><span>Duplicates</span><strong>{preview.duplicate_rows}</strong></div>
                </div>
                <div className={styles.previewRows}>
                  {preview.rows.map((row) => <div key={row.row_number}><span>{row.row_number}</span><div><strong>{row.legal_name ?? "Missing owner"}</strong><small>{row.property_address ?? row.phone ?? "No property or phone"} · {row.contact_point_count} contacts · {labelize(row.relationship_state)}</small></div><span className={`${styles.badge} ${styles[row.status]}`}>{labelize(row.status)}</span><p>{[...row.validation_errors, ...row.eligibility_reasons].join(" ") || (row.status === "duplicate" ? "Matches an existing Stonegate record; history will be preserved." : "Ready to call after import.")}</p></div>)}
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
              <label><span>Cohort</span><select name="cohort_id"><option value="">No cohort</option>{data.cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}</select></label>
              <label><span>Category</span><select name="category" onChange={(event) => setCostCategory(event.target.value)} value={costCategory}><option value="list_purchase">List purchase</option><option value="va_labor">VA labor</option><option value="data_enrichment">Data enrichment</option><option value="phone_number">Phone number</option><option value="voice_usage">Voice usage</option><option value="direct_mail">Direct mail</option><option value="ad_spend">Ad spend</option><option value="software">Software</option><option value="other">Other</option></select></label>
              <label><span>Related import</span><select name="import_batch_id"><option value="">No import</option>{data.import_batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.file_name}</option>)}</select></label>
              <label><span>Incurred on</span><input defaultValue={new Date().toISOString().slice(0, 10)} name="incurred_on" required type="date" /></label>
              {costCategory === "va_labor" ? <><label><span>Worker</span><select name="worker_user_id" required><option value="">Select worker</option>{activeUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label><label><span>Hours</span><input min="0.01" name="labor_hours" required step="0.01" type="number" /></label><label><span>Hourly rate ($)</span><input defaultValue="8" min="0" name="hourly_rate" required step="0.01" type="number" /></label></> : <label><span>Amount ($)</span><input min="0" name="amount" required step="0.01" type="number" /></label>}
              <label><span>Vendor</span><input name="vendor_name" /></label>
              <label className={styles.full}><span>Notes</span><textarea name="notes" rows={3} /></label>
              <button type="submit">Record cost</button>
            </form>
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
              <label><span>Cohort</span><select name="cohort_id"><option value="">No cohort</option>{data.cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name} · {callingModeLabel()}</option>)}</select></label>
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
          <section className={styles.section}><div className={styles.sectionHeader}><div><span>Import lineage</span><h3>Committed files</h3></div></div><div className={styles.picker}>{data.import_batches.map((batch) => <button className={selectedImportId === batch.id ? styles.selected : undefined} key={batch.id} onClick={() => setSelectedImportId(batch.id)} type="button"><strong>{batch.file_name}</strong><span>{batch.source_name}{batch.source_list_name ? ` · ${batch.source_list_name}` : ""} · {batch.imported_rows} new / {batch.matched_existing_rows} matched</span></button>)}{!data.import_batches.length ? <p className={styles.empty}>No files imported.</p> : null}</div></section>
          <section className={styles.section}><div className={styles.sectionHeader}><div><span>{selectedImport?.cohort_name ?? selectedImport?.mapping_name ?? "No import selected"}</span><h3>{selectedImport?.file_name ?? "Row-level results"}</h3></div>{selectedImport ? <strong>{selectedImport.total_rows}</strong> : null}</div><div className={styles.historyRows}>{selectedImport?.rows.map((row) => <div key={row.id}><span>{row.row_number}</span><div><strong>{row.legal_name ?? "Missing owner"}</strong><small>{row.property_address ?? row.phone ?? "No address or phone"} · {row.contact_point_count} contacts · {labelize(row.relationship_state)}</small></div><span className={`${styles.badge} ${styles[row.status.replace("imported_", "")]}`}>{labelize(row.status)}</span><p>{[...row.validation_errors, ...row.eligibility_reasons].join(" ") || (row.status === "matched_existing" ? "Existing history preserved and source appearance refreshed." : "Imported and ready.")}</p></div>)}{!selectedImport ? <p className={styles.empty}>Select an import to inspect every row.</p> : null}</div></section>
        </div>
      ) : null}
    </section>
  );
}
