"use client";

import { useAuth } from "@clerk/nextjs";
import { AlertTriangle, Link2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  BatchDialerCampaignMapping,
  BatchDialerCampaignMappings,
  BatchDialerCampaignMappingUpdateResponse,
} from "../../lib/api";
import styles from "./batchdialer-va-performance.module.css";

type MappingStatus = Record<
  string,
  { kind: "error" | "success"; text: string }
>;

type CampaignSelection = {
  purpose: "" | "seller_acquisition" | "investor_disposition";
  assetClass: "" | "house" | "land";
  dispositionCaseId: string;
};

function formatTimestamp(value: string | null, timeZone: string) {
  if (!value) return "Not routed";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
    timeZoneName: "short",
  }).format(parsed);
}

function errorDetail(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

function selectionValue(mapping: BatchDialerCampaignMapping) {
  return {
    purpose: mapping.workflow_purpose ?? "",
    assetClass: mapping.asset_class ?? "",
    dispositionCaseId: mapping.disposition_case_id ?? "",
  } satisfies CampaignSelection;
}

function sameSelection(left: CampaignSelection, right: CampaignSelection) {
  return left.purpose === right.purpose
    && left.assetClass === right.assetClass
    && left.dispositionCaseId === right.dispositionCaseId;
}

export function BatchDialerCampaignMappingsPanel({
  initialAvailable,
  initialData,
  timeZone,
}: {
  initialAvailable: boolean;
  initialData: BatchDialerCampaignMappings | null;
  timeZone: string;
}) {
  const { getToken } = useAuth();
  const [data, setData] = useState(initialData);
  const [selections, setSelections] = useState<Record<string, CampaignSelection>>(() =>
    Object.fromEntries(
      (initialData?.items ?? []).map((mapping) => [mapping.id, selectionValue(mapping)]),
    ),
  );
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(
    initialAvailable ? "" : "BatchDialer campaign routes are temporarily unavailable.",
  );
  const [status, setStatus] = useState<MappingStatus>({});
  const mountedRef = useRef(true);
  const requestSequenceRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    else headers["X-Dev-User-Email"] = devUserEmail;
    return headers;
  }, [devUserEmail, getToken]);

  useEffect(() => () => {
    mountedRef.current = false;
    requestSequenceRef.current += 1;
    requestControllerRef.current?.abort();
  }, []);

  const counts = useMemo(() => {
    const items = data?.items ?? [];
    return {
      house: items.filter((mapping) => mapping.asset_class === "house").length,
      land: items.filter((mapping) => mapping.asset_class === "land").length,
      investor: items.filter(
        (mapping) => mapping.workflow_purpose === "investor_disposition",
      ).length,
      needsClassification: items.filter((mapping) => mapping.workflow_purpose === null).length,
    };
  }, [data]);

  const loadMappings = useCallback(async () => {
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12_000);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/batchdialer/campaign-mappings`,
        {
          cache: "no-store",
          headers: await getHeaders(),
          signal: controller.signal,
        },
      );
      const payload = (await response.json().catch(() => null)) as
        | BatchDialerCampaignMappings
        | { detail?: string }
        | null;
      if (response.status === 401 || response.status === 403) {
        if (mountedRef.current && requestSequence === requestSequenceRef.current) {
          setData(null);
          setSelections({});
          setError("Your BatchDialer campaign-routing access expired or was removed.");
        }
        return;
      }
      if (!response.ok || !payload || !("items" in payload)) {
        throw new Error(
          errorDetail(payload, "BatchDialer campaign routes could not be refreshed."),
        );
      }
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setData(payload);
        setSelections(
          Object.fromEntries(
            payload.items.map((mapping) => [mapping.id, selectionValue(mapping)]),
          ),
        );
      }
    } catch (requestError) {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setError(
          requestError instanceof DOMException && requestError.name === "AbortError"
            ? "BatchDialer campaign routes timed out. The prior confirmed mappings remain visible."
            : requestError instanceof Error
              ? requestError.message
              : "BatchDialer campaign routes could not be refreshed.",
        );
      }
    } finally {
      window.clearTimeout(timeout);
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [apiBaseUrl, getHeaders]);

  const saveMapping = useCallback(async (mapping: BatchDialerCampaignMapping) => {
    const selected = selections[mapping.id] ?? selectionValue(mapping);
    if (
      mapping.workflow_purpose !== null &&
      !selected.purpose &&
      !window.confirm(
        "Clear this campaign route? New BatchDialer results will be held until it is mapped again.",
      )
    ) {
      return;
    }
    setBusyId(mapping.id);
    setStatus((current) => {
      const next = { ...current };
      delete next[mapping.id];
      return next;
    });
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/prospecting/batchdialer/campaign-mappings/${mapping.id}`,
        {
          method: "PATCH",
          cache: "no-store",
          headers: await getHeaders(),
          body: JSON.stringify({
            workflow_purpose: selected.purpose || null,
            asset_class: selected.purpose === "seller_acquisition"
              ? selected.assetClass || null
              : null,
            disposition_case_id: selected.purpose === "investor_disposition"
              ? selected.dispositionCaseId || null
              : null,
          }),
        },
      );
      const payload = (await response.json().catch(() => null)) as
        | BatchDialerCampaignMappingUpdateResponse
        | { detail?: string }
        | null;
      if (!response.ok || !payload || !("item" in payload)) {
        throw new Error(
          errorDetail(payload, "The campaign route could not be saved."),
        );
      }
      if (!mountedRef.current) return;
      setData((current) => current
        ? {
            ...current,
            items: current.items.map((item) => item.id === mapping.id ? payload.item : item),
          }
        : { items: [payload.item], disposition_targets: [] });
      setSelections((current) => ({
        ...current,
        [mapping.id]: selectionValue(payload.item),
      }));
      const classification = payload.item.workflow_purpose === "investor_disposition"
        ? "Investor dispositions"
        : payload.item.asset_class === "house"
          ? "Seller acquisition · House"
          : payload.item.asset_class === "land"
            ? "Seller acquisition · Land"
            : "Needs routing";
      const requeueMessage = payload.requeued_event_count
        ? ` ${payload.requeued_event_count.toLocaleString()} held qualified lead event(s) requeued.`
        : "";
      setStatus((current) => ({
        ...current,
        [mapping.id]: {
          kind: "success",
          text: `${classification} saved.${requeueMessage}`,
        },
      }));
    } catch (requestError) {
      if (!mountedRef.current) return;
      setStatus((current) => ({
        ...current,
        [mapping.id]: {
          kind: "error",
          text: requestError instanceof Error
            ? requestError.message
            : "The campaign route could not be saved.",
        },
      }));
    } finally {
      if (mountedRef.current) setBusyId("");
    }
  }, [apiBaseUrl, getHeaders, selections]);

  return (
    <section
      aria-busy={loading}
      aria-label="BatchDialer campaign routes"
      className={`${styles.panel} ${styles.classificationPanel}`}
    >
      <div className={styles.panelHeader}>
        <div>
          <span>Campaign routing</span>
          <h3>Tell Stonegate what each BatchDialer campaign is for</h3>
        </div>
        <button
          className={styles.refreshButton}
          disabled={loading}
          onClick={() => void loadMappings()}
          type="button"
        >
          <RefreshCw aria-hidden="true" className={loading ? styles.spinning : undefined} size={16} />
          {loading ? "Refreshing" : "Refresh campaigns"}
        </button>
      </div>

      <div className={styles.classificationHoldNotice} role="note">
        <AlertTriangle aria-hidden="true" size={18} />
        <p><strong>Results are held until a campaign is routed.</strong> Seller campaigns create seller leads in House or Land. Investor campaigns add interested buyers to the selected contracted deal in Dispositions; they never create seller leads.</p>
      </div>

      {data ? (
        <div aria-label="Campaign routing summary" className={styles.classificationSummary}>
          <div data-state={counts.needsClassification ? "needs" : "ready"}><span>Needs routing</span><strong>{counts.needsClassification}</strong></div>
          <div data-state="house"><span>House</span><strong>{counts.house}</strong></div>
          <div data-state="land"><span>Land</span><strong>{counts.land}</strong></div>
          <div data-state="investor"><span>Investor outreach</span><strong>{counts.investor}</strong></div>
        </div>
      ) : null}

      {error ? <p aria-live="assertive" className={styles.mappingError}>{error}</p> : null}
      {data?.items.length ? (
        <div className={styles.mappingList}>
          {data.items.map((mapping) => {
            const mappingStatus = status[mapping.id];
            const selected = selections[mapping.id] ?? selectionValue(mapping);
            const unchanged = sameSelection(selected, selectionValue(mapping));
            const selectionComplete = !selected.purpose
              || (selected.purpose === "seller_acquisition" && Boolean(selected.assetClass))
              || (selected.purpose === "investor_disposition" && Boolean(selected.dispositionCaseId));
            const classification = mapping.workflow_purpose === "investor_disposition"
              ? "Investor dispositions"
              : mapping.asset_class === "house"
                ? "Seller · House"
                : mapping.asset_class === "land"
                  ? "Seller · Land"
                  : "Needs routing";
            return (
              <div className={`${styles.mappingRow} ${styles.campaignMappingRow}`} key={mapping.id}>
                <div className={styles.mappingIdentity}>
                  <Link2 aria-hidden="true" size={17} />
                  <div>
                    <div className={styles.campaignMappingName}>
                      <strong>{mapping.provider_campaign_name}</strong>
                      <span data-state={mapping.workflow_purpose ?? "needs"}>{classification}</span>
                    </div>
                    <small>BatchDialer ID {mapping.provider_campaign_id} - {mapping.is_active ? "Active" : "Inactive"} ({mapping.provider_status})</small>
                    <small>{mapping.historical_lead_count.toLocaleString()} historical lead(s) - Last seen {formatTimestamp(mapping.last_seen_at, timeZone)}</small>
                    <small>Route updated {formatTimestamp(mapping.asset_class_mapped_at, timeZone)}</small>
                  </div>
                </div>
                <label>
                  <span>Campaign purpose</span>
                  <select
                    aria-label={`Campaign purpose for ${mapping.provider_campaign_name}`}
                    disabled={busyId === mapping.id}
                    onChange={(event) => setSelections((current) => ({
                      ...current,
                      [mapping.id]: {
                        purpose: event.target.value as CampaignSelection["purpose"],
                        assetClass: "",
                        dispositionCaseId: "",
                      },
                    }))}
                    value={selected.purpose}
                  >
                    <option value="">Needs routing</option>
                    <option value="seller_acquisition">Seller acquisition</option>
                    <option value="investor_disposition">Investor disposition</option>
                  </select>
                </label>
                {selected.purpose === "seller_acquisition" ? (
                  <label>
                    <span>Seller asset lane</span>
                    <select
                      aria-label={`Seller asset lane for ${mapping.provider_campaign_name}`}
                      disabled={busyId === mapping.id}
                      onChange={(event) => setSelections((current) => ({
                        ...current,
                        [mapping.id]: {
                          ...selected,
                          assetClass: event.target.value as CampaignSelection["assetClass"],
                        },
                      }))}
                      value={selected.assetClass}
                    >
                      <option value="">Choose House or Land</option>
                      <option value="house">House</option>
                      <option value="land">Land</option>
                    </select>
                  </label>
                ) : null}
                {selected.purpose === "investor_disposition" ? (
                  <label>
                    <span>Deal being marketed</span>
                    <select
                      aria-label={`Disposition deal for ${mapping.provider_campaign_name}`}
                      disabled={busyId === mapping.id}
                      onChange={(event) => setSelections((current) => ({
                        ...current,
                        [mapping.id]: { ...selected, dispositionCaseId: event.target.value },
                      }))}
                      value={selected.dispositionCaseId}
                    >
                      <option value="">Choose a contracted deal</option>
                      {(data.disposition_targets ?? []).map((target) => (
                        <option key={target.id} value={target.id}>
                          {target.label} · {target.status.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                    <small>
                      Recognized results: Qualified Buyer - Follow Up, Investor Interested,
                      Interested, Send Packet, Showing Requested or Appointment Set, Offer
                      Expected, Callback, Not Interested, Wrong Number, and Do Not Call.
                    </small>
                  </label>
                ) : null}
                <button
                  disabled={busyId === mapping.id || unchanged || !selectionComplete}
                  onClick={() => void saveMapping(mapping)}
                  type="button"
                >
                  {busyId === mapping.id ? "Saving..." : "Save route"}
                </button>
                <div className={styles.campaignMappingFeedback}>
                  {mapping.historical_asset_mismatch_count ? (
                    <p className={styles.mappingMismatch}>
                      <AlertTriangle aria-hidden="true" size={14} />
                      <span>
                        {mapping.historical_asset_mismatch_count.toLocaleString()} historical asset mismatch(es).
                        {mapping.historical_asset_mismatch_sample_lead_ids.length ? " Review samples: " : ""}
                        {mapping.historical_asset_mismatch_sample_lead_ids.map((leadId, index) => (
                          <span key={leadId}>
                            {index ? ", " : ""}<Link href={`/os/leads/${leadId}`}>{leadId.slice(0, 8)}</Link>
                          </span>
                        ))}
                      </span>
                    </p>
                  ) : null}
                  <p
                    aria-live="polite"
                    className={mappingStatus?.kind === "error" ? styles.mappingError : styles.mappingSuccess}
                  >
                    {mappingStatus?.text ?? ""}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      ) : data ? (
        <p className={styles.empty}>No BatchDialer campaigns have been discovered yet.</p>
      ) : null}
    </section>
  );
}
