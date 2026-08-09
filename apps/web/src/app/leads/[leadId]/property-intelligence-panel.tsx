"use client";

import { useAuth } from "@clerk/nextjs";
import {
  Camera,
  Database,
  Home,
  MapPin,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type { LeadDetail } from "../../lib/api";
import styles from "./page.module.css";
import { PropertyLocationMap } from "./property-location-map";

type Intelligence = LeadDetail["property_intelligence"];

function labelize(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function money(value: unknown) {
  return typeof value === "number"
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(value / 100)
    : "Not established";
}

function displayFact(value: unknown) {
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && value) return labelize(value);
  if (Array.isArray(value)) return value.map(String).join(", ");
  return "Unknown";
}

function displaySavedFact(intelligence: Intelligence, key: string) {
  const savedFact = intelligence.facts[key];
  const value = savedFact?.value;
  if (value === undefined || value === null) return "Unknown";
  if (savedFact.unit === "dollars" && typeof value === "number") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value);
  }
  if (savedFact.unit === "percent") return `${displayFact(value)}%`;
  const suffixes: Record<string, string> = {
    acres: "acres",
    days: "days",
    feet: "ft",
    square_feet: "sqft",
  };
  const suffix = savedFact.unit ? suffixes[savedFact.unit] : undefined;
  return suffix ? `${displayFact(value)} ${suffix}` : displayFact(value);
}

function numericSavedFact(intelligence: Intelligence, key: string) {
  const value = intelligence.facts[key]?.value;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function PropertyImage({ leadId, intelligence }: { leadId: string; intelligence: Intelligence }) {
  const { getToken } = useAuth();
  const [source, setSource] = useState("");
  const [sourceType, setSourceType] = useState(intelligence.image_source);
  const [selectedView, setSelectedView] = useState(
    intelligence.image_views?.[0] ?? "listing",
  );
  const availableViews = intelligence.image_views?.length
    ? intelligence.image_views
    : ["listing"];
  const activeView = availableViews.includes(selectedView)
    ? selectedView
    : availableViews[0];
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

  useEffect(() => {
    if (!intelligence.image_available || !intelligence.image_url) {
      return;
    }
    let active = true;
    let objectUrl = "";
    async function loadImage() {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devUserEmail };
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${leadId}/property-image?view=${activeView}`,
        { headers },
      );
      if (!response.ok) throw new Error("Property image unavailable.");
      objectUrl = URL.createObjectURL(await response.blob());
      if (active) {
        setSource(objectUrl);
        setSourceType(
          response.headers.get("X-Property-Image-Source") ?? intelligence.image_source,
        );
      }
    }
    loadImage().catch(() => active && setSource(""));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    activeView,
    apiBaseUrl,
    devUserEmail,
    getToken,
    intelligence.image_available,
    intelligence.image_source,
    intelligence.image_url,
    leadId,
  ]);

  function chooseView(view: string) {
    setSource("");
    setSelectedView(view);
  }

  const attribution = !intelligence.image_available
    ? "No licensed image returned"
    : sourceType === "realestateapi_listing"
      ? "RealEstateAPI licensed listing media"
      : intelligence.image_attribution ?? "Stonegate property media";

  return (
    <div className={styles.propertyHeroImage}>
      {source && intelligence.image_available ? (
        <Image alt="Property exterior" height={400} src={source} unoptimized width={640} />
      ) : (
        <div className={styles.propertyImagePlaceholder}>
          <Home size={42} />
          <strong>No property photo available</strong>
          <span>A licensed listing image or Stonegate inspection photo will appear here.</span>
        </div>
      )}
      <div className={styles.propertyImageCaption}>
        <Camera size={14} />
        <span>{attribution}</span>
        {intelligence.imagery_date ? <small>{intelligence.imagery_date}</small> : null}
      </div>
      {availableViews.length > 1 ? (
        <div className={styles.propertyImageViews} aria-label="Property image view">
          {availableViews.map((view) => (
            <button
              aria-pressed={activeView === view}
              key={view}
              onClick={() => chooseView(view)}
              type="button"
            >
              {labelize(view)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function PropertyIntelligencePanel({ lead }: { lead: LeadDetail }) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intelligence = lead.property_intelligence;
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

  useEffect(() => {
    if (!["queued", "processing"].includes(intelligence.research_status)) return;
    const interval = window.setInterval(() => router.refresh(), 5000);
    return () => window.clearInterval(interval);
  }, [intelligence.research_status, router]);

  async function refreshResearch() {
    setRefreshing(true);
    setError(null);
    try {
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : { "X-Dev-User-Email": devUserEmail };
      const response = await fetch(
        `${apiBaseUrl}/api/v1/leads/${lead.id}/property-intelligence/refresh`,
        { method: "POST", headers },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Property research could not be requested.");
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Property research could not be requested.");
    } finally {
      setRefreshing(false);
    }
  }

  const status = intelligence.is_stale ? "stale" : intelligence.research_status;
  const valuation = intelligence.valuation;
  const isLand = lead.asset_class === "land";
  const houseFacts = [
    ["Property type", displaySavedFact(intelligence, "property_type")],
    ["Bedrooms", displaySavedFact(intelligence, "bedrooms")],
    ["Bathrooms", displaySavedFact(intelligence, "bathrooms")],
    ["Living area", displaySavedFact(intelligence, "square_footage")],
    ["Lot area", displaySavedFact(intelligence, "lot_size_acres")],
    ["Year built", displaySavedFact(intelligence, "year_built")],
    ["Units", displaySavedFact(intelligence, "unit_count")],
    ["Stories", displaySavedFact(intelligence, "stories")],
    ["Subdivision", displaySavedFact(intelligence, "subdivision")],
    ["Parcel / APN", displaySavedFact(intelligence, "parcel_id")],
    ["Construction", displaySavedFact(intelligence, "construction_type")],
    ["Recorded condition", displaySavedFact(intelligence, "building_condition")],
  ];
  const landFacts = [
    ["Property type", displaySavedFact(intelligence, "property_type")],
    ["Parcel / APN", displaySavedFact(intelligence, "parcel_id")],
    ["Lot area", displaySavedFact(intelligence, "lot_size_acres")],
    ["Lot square footage", displaySavedFact(intelligence, "lot_size")],
    ["Lot number", displaySavedFact(intelligence, "lot_number")],
    ["Subdivision", displaySavedFact(intelligence, "subdivision")],
    ["Legal description", displaySavedFact(intelligence, "legal_description")],
    ["Zoning record", displaySavedFact(intelligence, "zoning")],
    ["Water record", displaySavedFact(intelligence, "water")],
    ["Sewer record", displaySavedFact(intelligence, "sewer")],
    ["Flood zone", displaySavedFact(intelligence, "flood_zone")],
    ["Assessed land value", displaySavedFact(intelligence, "assessed_land_value")],
  ];
  const housePropertySignals = [
    ["Last sale date", displaySavedFact(intelligence, "last_sale_date")],
    ["Last sale price", displaySavedFact(intelligence, "last_sale_price")],
    ["Estimated equity", displaySavedFact(intelligence, "estimated_equity_amount")],
    ["Estimated equity %", displaySavedFact(intelligence, "estimated_equity_percentage")],
    ["Estimated loan balance", displaySavedFact(intelligence, "estimated_loan_balance")],
    ["Estimated LTV", displaySavedFact(intelligence, "estimated_loan_to_value")],
    ["Market status", displaySavedFact(intelligence, "market_status")],
    ["Current listing price", displaySavedFact(intelligence, "current_listing_price")],
    ["Days on market", displaySavedFact(intelligence, "days_on_market")],
    ["Assessed value", displaySavedFact(intelligence, "assessed_total_value")],
    ["Annual property tax", displaySavedFact(intelligence, "annual_property_tax")],
    ["Active liens", displaySavedFact(intelligence, "active_lien_count")],
    ["Lien reported", displaySavedFact(intelligence, "lien_reported")],
    ["Pre-foreclosure", displaySavedFact(intelligence, "pre_foreclosure")],
    ["Vacant", displaySavedFact(intelligence, "vacant")],
    ["Owner occupied", displaySavedFact(intelligence, "owner_occupied")],
    ["Free and clear", displaySavedFact(intelligence, "free_and_clear")],
  ];
  const landPropertySignals = [
    ["Last sale date", displaySavedFact(intelligence, "last_sale_date")],
    ["Last sale price", displaySavedFact(intelligence, "last_sale_price")],
    ["Market status", displaySavedFact(intelligence, "market_status")],
    ["Current listing price", displaySavedFact(intelligence, "current_listing_price")],
    ["Days on market", displaySavedFact(intelligence, "days_on_market")],
    ["Assessed land value", displaySavedFact(intelligence, "assessed_land_value")],
    ["Assessed total value", displaySavedFact(intelligence, "assessed_total_value")],
    ["Annual property tax", displaySavedFact(intelligence, "annual_property_tax")],
    ["Recorded owner", displaySavedFact(intelligence, "recorded_owner")],
    ["Ownership length", displaySavedFact(intelligence, "ownership_length_months")],
    ["Active liens", displaySavedFact(intelligence, "active_lien_count")],
    ["Lien reported", displaySavedFact(intelligence, "lien_reported")],
  ];
  const facts = isLand ? landFacts : houseFacts;
  const propertySignals = isLand ? landPropertySignals : housePropertySignals;
  const houseAdditionalFacts = [
    ["School district", "school_district"],
    ["Property class", "property_class"],
    ["Building style", "building_style"],
    ["Zoning", "zoning"],
    ["Municipality", "municipality"],
    ["HOA fee", "hoa_fee"],
    ["Garage", "garage_type"],
    ["Basement", "basement"],
    ["Pool", "pool"],
    ["Roof", "roof_cover"],
    ["Air conditioning", "air_conditioning"],
    ["Heating", "heating_type"],
    ["Sewer", "sewer"],
    ["Water", "water"],
    ["Flood zone", "flood_zone"],
    ["Recorded owner", "recorded_owner"],
    ["Recorded co-owner", "recorded_co_owner"],
    ["Owner company", "owner_company"],
    ["Ownership length", "ownership_length_months"],
  ];
  const landAdditionalFacts = [
    ["County", "county"],
    ["Municipality", "municipality"],
    ["School district", "school_district"],
    ["Property class", "property_class"],
    ["Flood description", "flood_zone_description"],
    ["Tax assessment year", "tax_assessment_year"],
    ["Recorded co-owner", "recorded_co_owner"],
    ["Owner company", "owner_company"],
    ["Owner mailing street", "owner_mailing_street"],
    ["Owner mailing city", "owner_mailing_city"],
    ["Owner mailing state", "owner_mailing_state"],
  ];
  const additionalFacts = (isLand ? landAdditionalFacts : houseAdditionalFacts).map(
    ([label, key]) => [label, displaySavedFact(intelligence, key)],
  );
  const propertyAddress = lead.property_street_address
    ? [
        lead.property_street_address,
        lead.property_city,
        lead.property_state,
        lead.property_postal_code,
      ].filter(Boolean).join(", ")
    : [
        lead.property_parcel_id ? `APN ${lead.property_parcel_id}` : null,
        lead.property_county,
        lead.property_state,
      ].filter(Boolean).join(", ");
  const propertyLocality = [
    lead.property_city || lead.property_county,
    [lead.property_state, lead.property_postal_code].filter(Boolean).join(" "),
  ].filter(Boolean).join(", ");
  const propertyIdentity = lead.property_street_address
    || (lead.property_parcel_id ? `APN ${lead.property_parcel_id}` : "Property identity pending");

  return (
    <section className={`${styles.sectionPanel} ${styles.propertyIntelligencePanel}`}>
      <div className={styles.propertyIntelligenceHeader}>
        <div>
          <span className={styles.sectionEyebrow}>Property intelligence</span>
          <h2>{propertyIdentity}</h2>
          <p><MapPin size={14} />{propertyLocality}</p>
        </div>
        <div className={styles.propertyResearchActions}>
          <span className={styles.propertyResearchStatus} data-status={status}>
            {labelize(status)}
          </span>
          <button disabled={refreshing} onClick={refreshResearch} type="button">
            <RefreshCw className={refreshing ? styles.spin : undefined} size={15} />
            {refreshing ? "Requesting..." : "Refresh research"}
          </button>
        </div>
      </div>

      <div className={styles.propertyHeroGrid}>
        <PropertyImage intelligence={intelligence} leadId={lead.id} />
        <div className={styles.propertyResearchSummary}>
          <div><span>Profile complete</span><strong>{intelligence.completeness_score}%</strong></div>
          <div><span>{isLand && !intelligence.market_context.land_valuation ? "Research confidence" : "Valuation confidence"}</span><strong>{intelligence.confidence_score}%</strong></div>
          <div><span>{isLand ? "Saved land sales" : "Selected comps"}</span><strong>{intelligence.comparables.length}</strong></div>
          <div><span>Snapshot</span><strong>{intelligence.version_number ? `v${intelligence.version_number}` : "Pending"}</strong></div>
          <small>
            {intelligence.captured_at
              ? `Evidence captured ${new Date(intelligence.captured_at).toLocaleString()}`
              : "Research will run after the property identity is confirmed."}
          </small>
        </div>
      </div>

      {intelligence.last_error || error ? (
        <div className={styles.propertyResearchWarning}>
          <TriangleAlert size={16} />
          <span>{error ?? intelligence.last_error}</span>
        </div>
      ) : null}

      <PropertyLocationMap
        address={propertyAddress}
        latitude={numericSavedFact(intelligence, "latitude")}
        longitude={numericSavedFact(intelligence, "longitude")}
      />

      <div className={styles.propertyIntelligenceSections}>
        <div className={styles.propertyFactSection}>
          <h3>Verified property facts</h3>
          <dl>
            {facts.map(([label, value]) => (
              <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
            ))}
          </dl>
        </div>

        <div className={styles.propertyValueSection}>
          <h3>{isLand ? "Land value evidence" : "Saved value evidence"}</h3>
          {isLand ? (
            <>
              <div className={styles.propertyValueCards}>
                <div><span>Supported land value</span><strong>{money(valuation.land_value_point_cents)}</strong></div>
                <div><span>Supported low</span><strong>{money(valuation.land_value_low_cents)}</strong></div>
                <div><span>Supported high</span><strong>{money(valuation.land_value_high_cents)}</strong></div>
                <div><span>External benchmark</span><strong>{money(valuation.estimated_value_cents)}</strong></div>
              </div>
              <p>{String(valuation.source_note ?? "Land value has not been established from reviewed comparable sales.")}</p>
            </>
          ) : (
            <>
              <div className={styles.propertyValueCards}>
                <div><span>Stonegate ARV</span><strong>{money(valuation.arv_point_cents)}</strong></div>
                <div><span>Supported low</span><strong>{money(valuation.arv_low_cents)}</strong></div>
                <div><span>Supported high</span><strong>{money(valuation.arv_high_cents)}</strong></div>
                <div><span>External benchmark</span><strong>{money(valuation.estimated_value_cents)}</strong></div>
              </div>
              <p>{String(valuation.source_note ?? "Value evidence has not been collected yet.")}</p>
            </>
          )}
        </div>
      </div>

      <div className={styles.propertySignalSection}>
        <div>
          <h3>Property and market signals</h3>
          <p>{isLand ? "Recorded zoning, utilities, access, flood, and environmental facts are screening evidence—not legal opinions or guarantees that a parcel is buildable." : "Provider estimates are research signals, not seller-confirmed balances or offer math."}</p>
        </div>
        <dl>
          {propertySignals.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
          ))}
        </dl>
      </div>

      <details className={styles.propertyEvidenceDetails}>
        <summary>Additional property record</summary>
        <dl className={styles.propertyAdditionalFacts}>
          {additionalFacts.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
          ))}
        </dl>
      </details>

      <div className={styles.propertyCompPreview}>
        <div className={styles.propertySectionTitle}>
          <div><Database size={16} /><h3>{isLand ? "Land sale evidence already on file" : "Comparable evidence already on file"}</h3></div>
          <Link href={`/os/leads/${lead.id}?tab=valuation${isLand ? "" : "#valuation-analysis"}`}>
            {isLand ? "Open Land valuation" : "Open full valuation"}
          </Link>
        </div>
        {intelligence.comparables.length ? (
          <div className={styles.propertyCompRows}>
            {intelligence.comparables.slice(0, 4).map((comp, index) => (
              <div key={String(comp.provider_id ?? comp.formatted_address ?? index)}>
                <strong>{String(comp.formatted_address ?? "Comparable sale")}</strong>
                <span>{money(comp.price_cents)}</span>
                <small>
                  {comp.sale_date ? String(comp.sale_date) : "Sale date unavailable"}
                  {typeof comp.distance_miles === "number" ? ` / ${comp.distance_miles.toFixed(2)} mi` : ""}
                  {comp.comp_grade ? ` / Grade ${String(comp.comp_grade)}` : ""}
                </small>
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.emptyState}>{isLand ? "Reviewed land sale evidence has not been added yet." : "Comparable evidence is still being researched."}</p>
        )}
      </div>

      <details className={styles.propertyEvidenceDetails}>
        <summary>Sources, conflicts and freshness</summary>
        <div>
          <section>
            <h4>Sources</h4>
            {intelligence.sources.length ? (
              <ul>{intelligence.sources.map((source, index) => (
                <li key={`${String(source.source)}-${index}`}>
                  <strong>{labelize(String(source.source ?? "source"))}</strong>
                  <span>{labelize(String(source.role ?? "supporting evidence"))}</span>
                </li>
              ))}</ul>
            ) : <p>No provider sources captured yet.</p>}
          </section>
          <section>
            <h4>Review items</h4>
            {intelligence.conflicts.length ? (
              <ul>{intelligence.conflicts.slice(0, 8).map((conflict, index) => (
                <li key={index}>{String(conflict.message ?? conflict.reason ?? "Provider fact conflict")}</li>
              ))}</ul>
            ) : <p>No material source conflicts are recorded.</p>}
          </section>
        </div>
      </details>
    </section>
  );
}
