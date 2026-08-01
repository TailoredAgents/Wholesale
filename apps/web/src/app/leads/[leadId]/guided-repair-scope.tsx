"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { RepairEstimateItem } from "./repair-estimate-control";
import styles from "./page.module.css";

type ScopeStatus =
  | "unknown"
  | "no_work"
  | "repair"
  | "replace"
  | "specialist_review";
type Severity = "minor" | "standard" | "extensive";

type CatalogRate = {
  low_cents: number;
  expected_cents: number;
  high_cents: number;
};

type CatalogItem = {
  category: string;
  label: string;
  unit: string;
  default_quantity: number;
  quantity_basis: string;
  repair: CatalogRate;
  replace: CatalogRate;
  minimum_cents: number;
  specialist_recommended: boolean;
};

type RepairCatalog = {
  version: string;
  market_label: string;
  effective_date: string;
  source_note: string;
  items: CatalogItem[];
};

type Props = {
  contingencyPercentage: number;
  disabled: boolean;
  items: RepairEstimateItem[];
  leadId: string;
  onChange: (items: RepairEstimateItem[]) => void;
  repairLevel: string;
};

const SEVERITY_FACTORS: Record<Severity, number> = {
  minor: 0.75,
  standard: 1,
  extensive: 1.35,
};

const PRESETS: Record<string, Partial<Record<string, ScopeStatus>>> = {
  light: {
    kitchen: "repair",
    bathrooms: "repair",
    flooring: "repair",
    paint_drywall: "repair",
    landscaping: "repair",
    cleanup: "repair",
  },
  moderate: {
    roof: "repair",
    hvac: "repair",
    plumbing: "unknown",
    electrical: "unknown",
    kitchen: "replace",
    bathrooms: "replace",
    flooring: "replace",
    paint_drywall: "replace",
    windows_doors: "repair",
    exterior: "repair",
    landscaping: "repair",
    permits: "repair",
    cleanup: "replace",
  },
  heavy: {
    roof: "replace",
    hvac: "replace",
    plumbing: "specialist_review",
    electrical: "specialist_review",
    foundation: "unknown",
    kitchen: "replace",
    bathrooms: "replace",
    flooring: "replace",
    paint_drywall: "replace",
    windows_doors: "replace",
    exterior: "replace",
    landscaping: "replace",
    permits: "replace",
    cleanup: "replace",
  },
  structural: {
    roof: "replace",
    hvac: "replace",
    plumbing: "specialist_review",
    electrical: "specialist_review",
    foundation: "specialist_review",
    kitchen: "replace",
    bathrooms: "replace",
    flooring: "replace",
    paint_drywall: "replace",
    windows_doors: "replace",
    exterior: "replace",
    landscaping: "replace",
    permits: "replace",
    cleanup: "replace",
  },
};

export function GuidedRepairScope({
  contingencyPercentage,
  disabled,
  items,
  leadId,
  onChange,
  repairLevel,
}: Props) {
  const { getToken } = useAuth();
  const [catalog, setCatalog] = useState<RepairCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  const getHeaders = useCallback(async () => {
    const token = await getToken().catch(() => null);
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      headers["X-Dev-User-Email"] = devUserEmail;
    }
    return headers;
  }, [devUserEmail, getToken]);

  useEffect(() => {
    const controller = new AbortController();
    async function loadCatalog() {
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/v1/leads/${leadId}/repair-catalog`,
          { headers: await getHeaders(), signal: controller.signal },
        );
        if (!response.ok) throw new Error("Unable to load the repair catalog.");
        setCatalog((await response.json()) as RepairCatalog);
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(caught instanceof Error ? caught.message : "Unable to load repair catalog.");
        }
      }
    }
    void loadCatalog();
    return () => controller.abort();
  }, [apiBaseUrl, getHeaders, leadId]);

  const itemByCategory = useMemo(
    () => new Map(items.map((item) => [item.category, item])),
    [items],
  );
  const scenario = useMemo(() => {
    if (!catalog) return null;
    const subtotal = items.reduce(
      (total, item) => {
        const entry = catalog.items.find((candidate) => candidate.category === item.category);
        if (!entry) return total;
        const range = itemRange(entry, item);
        return {
          low: total.low + range.low,
          expected: total.expected + range.expected,
          high: total.high + range.high,
          unknown:
            total.unknown +
            (item.scope_status === "unknown" || item.scope_status === "specialist_review"
              ? range.expected
              : 0),
        };
      },
      { low: 0, expected: 0, high: 0, unknown: 0 },
    );
    const factor = 1 + contingencyPercentage / 100;
    return {
      ...subtotal,
      low: Math.round(subtotal.low * factor),
      expected: Math.round(subtotal.expected * factor),
      high: Math.round(subtotal.high * factor),
    };
  }, [catalog, contingencyPercentage, items]);

  function updateCategory(entry: CatalogItem, patch: Partial<RepairEstimateItem>) {
    const current = itemByCategory.get(entry.category);
    const next: RepairEstimateItem = {
      category: entry.category,
      scope_status: current?.scope_status ?? "unknown",
      severity: current?.severity ?? "standard",
      quantity: current?.quantity ?? entry.default_quantity,
      unit: entry.unit,
      pricing_method: "catalog",
      evidence_source: current?.evidence_source ?? "not_provided",
      confirmation_status: current?.confirmation_status ?? "unconfirmed",
      inspection_status: current?.inspection_status ?? "not_inspected",
      ...current,
      ...patch,
      catalog_version: catalog?.version ?? current?.catalog_version,
    };
    onChange([...items.filter((item) => item.category !== entry.category), next]);
  }

  function removeCategory(category: string) {
    onChange(items.filter((item) => item.category !== category));
  }

  function applyPreset() {
    if (!catalog) return;
    const preset = PRESETS[repairLevel] ?? PRESETS.moderate;
    onChange(
      catalog.items
        .filter((entry) => preset[entry.category])
        .map((entry) => ({
          category: entry.category,
          scope_status: preset[entry.category],
          severity:
            repairLevel === "light"
              ? "minor"
              : repairLevel === "heavy" || repairLevel === "structural"
                ? "extensive"
                : "standard",
          quantity: entry.default_quantity,
          unit: entry.unit,
          pricing_method: "catalog",
          evidence_source: "not_provided",
          confirmation_status: "unconfirmed",
          inspection_status:
            preset[entry.category] === "specialist_review"
              ? "specialist_needed"
              : "not_inspected",
          catalog_version: catalog.version,
        })),
    );
  }

  if (error) return <p className={styles.repairEvidenceError}>{error}</p>;
  if (!catalog) {
    return <p className={styles.repairCatalogLoading}>Loading repair catalog...</p>;
  }

  return (
    <section className={styles.guidedRepairScope} aria-label="Guided repair scope">
      <header className={styles.guidedRepairHeader}>
        <div>
          <strong>Guided Georgia scope</strong>
          <span>
            {catalog.version} · {catalog.market_label}
          </span>
        </div>
        <button disabled={disabled} onClick={applyPreset} type="button">
          Apply {repairLevel.replaceAll("_", " ")} preset
        </button>
      </header>

      {scenario ? (
        <dl className={styles.repairScenarioStrip}>
          <div>
            <dt>Low total</dt>
            <dd>{formatMoney(scenario.low)}</dd>
          </div>
          <div>
            <dt>Expected total</dt>
            <dd>{formatMoney(scenario.expected)}</dd>
          </div>
          <div>
            <dt>High total</dt>
            <dd>{formatMoney(scenario.high)}</dd>
          </div>
          <div>
            <dt>Unknown allowance</dt>
            <dd>{formatMoney(scenario.unknown)}</dd>
          </div>
        </dl>
      ) : null}

      <div className={styles.guidedRepairList}>
        {catalog.items.map((entry) => {
          const item = itemByCategory.get(entry.category);
          const status = item?.scope_status ?? "";
          const range = item ? itemRange(entry, item) : null;
          return (
            <article key={entry.category}>
              <div className={styles.guidedRepairPrimary}>
                <strong>{entry.label}</strong>
                <label>
                  <span>Work state</span>
                  <select
                    aria-label={`${entry.label} work state`}
                    disabled={disabled}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (!value) removeCategory(entry.category);
                      else {
                        updateCategory(entry, {
                          scope_status: value as ScopeStatus,
                          inspection_status:
                            value === "specialist_review"
                              ? "specialist_needed"
                              : "not_inspected",
                        });
                      }
                    }}
                    value={status}
                  >
                    <option value="">Not assessed</option>
                    <option value="unknown">Unknown</option>
                    <option value="no_work">No work</option>
                    <option value="repair">Repair</option>
                    <option value="replace">Replace</option>
                    <option value="specialist_review">Specialist review</option>
                  </select>
                </label>
                {item && status !== "no_work" ? (
                  <>
                    <label>
                      <span>Scope</span>
                      <select
                        disabled={disabled}
                        onChange={(event) =>
                          updateCategory(entry, {
                            severity: event.target.value as Severity,
                          })
                        }
                        value={item.severity ?? "standard"}
                      >
                        <option value="minor">Minor</option>
                        <option value="standard">Standard</option>
                        <option value="extensive">Extensive</option>
                      </select>
                    </label>
                    <label>
                      <span>Quantity</span>
                      <div className={styles.repairQuantityInput}>
                        <input
                          disabled={disabled}
                          inputMode="decimal"
                          min="0.01"
                          onChange={(event) =>
                            updateCategory(entry, {
                              quantity: Number(event.target.value),
                            })
                          }
                          step="0.1"
                          type="number"
                          value={item.quantity ?? entry.default_quantity}
                        />
                        <span>{unitLabel(entry.unit)}</span>
                      </div>
                    </label>
                  </>
                ) : (
                  <div />
                )}
                <div className={styles.guidedRepairRange}>
                  <span>Expected range</span>
                  <strong>
                    {range
                      ? `${formatMoney(range.low)} - ${formatMoney(range.high)}`
                      : "--"}
                  </strong>
                  {range ? <small>{formatMoney(range.expected)} expected</small> : null}
                </div>
              </div>

              {item && status !== "no_work" ? (
                <details className={styles.guidedRepairEvidence}>
                  <summary>Evidence and override</summary>
                  <div>
                    <label>
                      <span>Evidence</span>
                      <select
                        disabled={disabled}
                        onChange={(event) =>
                          updateCategory(entry, {
                            evidence_source: event.target.value,
                          })
                        }
                        value={item.evidence_source ?? "not_provided"}
                      >
                        <option value="not_provided">Not provided</option>
                        <option value="seller_report">Seller report</option>
                        <option value="staff_observation">Staff observation</option>
                        <option value="walkthrough">Walkthrough</option>
                        <option value="contractor_bid">Contractor bid</option>
                        <option value="document">Document</option>
                        <option value="other">Other</option>
                      </select>
                    </label>
                    <label>
                      <span>Confirmation</span>
                      <select
                        disabled={disabled}
                        onChange={(event) =>
                          updateCategory(entry, {
                            confirmation_status: event.target.value,
                          })
                        }
                        value={item.confirmation_status ?? "unconfirmed"}
                      >
                        <option value="unconfirmed">Unconfirmed</option>
                        <option value="user_confirmed">User confirmed</option>
                        <option value="walkthrough_verified">Walkthrough verified</option>
                        <option value="contractor_verified">Contractor verified</option>
                      </select>
                    </label>
                    <label>
                      <span>Manual amount</span>
                      <div className={styles.moneyInput}>
                        <span>$</span>
                        <input
                          disabled={disabled}
                          inputMode="decimal"
                          min="0"
                          onChange={(event) =>
                            updateCategory(entry, {
                              manual_override_cents: event.target.value
                                ? Math.round(Number(event.target.value) * 100)
                                : null,
                            })
                          }
                          placeholder="Use system"
                          step="100"
                          type="number"
                          value={item.manual_override_cents ? item.manual_override_cents / 100 : ""}
                        />
                      </div>
                    </label>
                    <label>
                      <span>Override reason</span>
                      <input
                        disabled={disabled || !item.manual_override_cents}
                        maxLength={500}
                        onChange={(event) =>
                          updateCategory(entry, {
                            override_reason: event.target.value,
                          })
                        }
                        placeholder="Required with manual amount"
                        value={item.override_reason ?? ""}
                      />
                    </label>
                    <label className={styles.guidedRepairWide}>
                      <span>Scope notes</span>
                      <input
                        disabled={disabled}
                        maxLength={500}
                        onChange={(event) => updateCategory(entry, { details: event.target.value })}
                        placeholder={entry.quantity_basis}
                        value={item.details ?? ""}
                      />
                    </label>
                  </div>
                </details>
              ) : null}
            </article>
          );
        })}
      </div>
      <small className={styles.repairCatalogNote}>{catalog.source_note}</small>
    </section>
  );
}

function itemRange(entry: CatalogItem, item: RepairEstimateItem) {
  if (item.scope_status === "no_work") return { low: 0, expected: 0, high: 0 };
  if (item.pricing_method !== "catalog") {
    const expected =
      item.manual_override_cents ?? item.estimated_cost_cents ?? 0;
    return {
      low: Math.min(item.system_low_cents ?? expected, expected),
      expected,
      high: Math.max(item.system_high_cents ?? expected, expected),
    };
  }
  if (
    item.catalog_version &&
    item.system_low_cents !== null &&
    item.system_low_cents !== undefined &&
    item.system_high_cents !== null &&
    item.system_high_cents !== undefined &&
    item.estimated_cost_cents !== null &&
    item.estimated_cost_cents !== undefined
  ) {
    return {
      low: item.system_low_cents,
      expected: item.estimated_cost_cents,
      high: item.system_high_cents,
    };
  }
  const quantity = item.quantity ?? entry.default_quantity;
  const severity = item.severity ?? "standard";
  const factor = SEVERITY_FACTORS[severity];
  const apply = (value: number, multiplier = 1) =>
    Math.max(
      entry.minimum_cents,
      Math.round(value * quantity * multiplier),
    );
  let system: { low: number; expected: number; high: number };
  if (item.scope_status === "unknown") {
    const reserve = entry.specialist_recommended ? 0.4 : 0.25;
    system = {
      low: 0,
      expected: Math.round(entry.replace.expected_cents * quantity * reserve),
      high: apply(entry.replace.high_cents),
    };
  } else if (item.scope_status === "specialist_review") {
    system = {
      low: apply(entry.repair.low_cents),
      expected: apply(entry.replace.expected_cents),
      high: apply(entry.replace.high_cents, 1.25),
    };
  } else {
    const range = item.scope_status === "replace" ? entry.replace : entry.repair;
    system = {
      low: apply(range.low_cents, factor),
      expected: apply(range.expected_cents, factor),
      high: apply(range.high_cents, factor),
    };
  }
  if (
    item.manual_override_cents === null ||
    item.manual_override_cents === undefined
  ) {
    return system;
  }
  return {
    low: Math.min(system.low, item.manual_override_cents),
    expected: item.manual_override_cents,
    high: Math.max(system.high, item.manual_override_cents),
  };
}

function formatMoney(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function unitLabel(unit: string) {
  return unit.replaceAll("_", " ");
}
