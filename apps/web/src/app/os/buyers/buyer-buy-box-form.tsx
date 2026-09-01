"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useMemo, useState } from "react";

import type {
  BuyerBuyBoxAsset,
  BuyerBuyBoxCriteria,
  BuyerBuyBoxGeography,
  BuyerBuyBoxSummary,
  BuyerBuyBoxVersion,
} from "../../lib/api";
import { labelize } from "../os-utils";
import styles from "./buyers.module.css";

type SaveStatus = "idle" | "saving" | "error";

const strategies = [
  "wholesale_assignment", "double_close", "fix_and_flip", "buy_and_hold", "wholetail",
  "novation", "new_construction", "development", "land_hold", "owner_finance",
];
const fundingMethods = ["cash", "hard_money", "private_money", "conventional", "dscr", "seller_finance", "other"];
const housePropertyTypes = ["single_family", "townhouse", "condo", "duplex", "triplex", "fourplex", "multifamily", "mobile_home", "other_residential"];
const rehabLevels = ["none", "light", "medium", "heavy", "full_gut"];
const occupancies = ["vacant", "owner_occupied", "tenant_occupied"];
const landUses = ["residential", "agricultural", "recreational", "commercial", "industrial", "timber", "development", "hold"];
const accessPreferences = ["paved_road", "gravel_road", "dirt_road", "legal_access", "landlocked_review"];
const utilityPreferences = ["electric", "public_water", "well", "public_sewer", "septic", "gas", "none"];
const terrainPreferences = ["flat", "rolling", "sloped", "mountainous", "wooded", "cleared", "mixed"];

function text(form: FormData, key: string) {
  return String(form.get(key) ?? "").trim();
}

function checked(form: FormData, key: string) {
  return form.getAll(key).map(String);
}

function optionalNumber(form: FormData, key: string) {
  const value = text(form, key);
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function optionalInteger(form: FormData, key: string) {
  const value = optionalNumber(form, key);
  return value === null ? null : Number.isInteger(value) ? value : Number.NaN;
}

function optionalCents(form: FormData, key: string) {
  const value = optionalNumber(form, key);
  return value === null ? null : Math.round(value * 100);
}

function requireOrderedRange(
  minimum: number | null,
  maximum: number | null,
  label: string,
) {
  if (minimum !== null && maximum !== null && minimum > maximum) {
    throw new Error(`Minimum ${label} cannot be higher than maximum ${label}.`);
  }
}

function dollars(cents: number | null | undefined) {
  return cents === null || cents === undefined ? "" : String(cents / 100);
}

function listLines(value: string) {
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function geographyLines(items: BuyerBuyBoxGeography[]) {
  return items.filter((item) => item.jurisdiction !== "radius").map((item) => {
    if (item.jurisdiction === "state" || item.jurisdiction === "postal_code") return item.value;
    return `${item.value}, ${item.state ?? ""}`.replace(/, $/, "");
  }).join("\n");
}

function radiusGeography(items: BuyerBuyBoxGeography[]) {
  return items.find((item) => item.jurisdiction === "radius") ?? null;
}

function parseGeographies(value: string, label: string): BuyerBuyBoxGeography[] {
  return listLines(value).map((line) => {
    if (/^\d{5}$/.test(line)) {
      return { jurisdiction: "postal_code", value: line, state: null, latitude: null, longitude: null, radius_miles: null };
    }
    if (/^[a-z]{2}$/i.test(line)) {
      return { jurisdiction: "state", value: line.toUpperCase(), state: null, latitude: null, longitude: null, radius_miles: null };
    }
    const county = line.match(/^(.+?\s+County)\s*,\s*([a-z]{2})$/i);
    if (county) {
      return { jurisdiction: "county", value: county[1].trim(), state: county[2].toUpperCase(), latitude: null, longitude: null, radius_miles: null };
    }
    const city = line.match(/^(.+?)\s*,\s*([a-z]{2})$/i);
    if (city) {
      return { jurisdiction: "city", value: city[1].trim(), state: city[2].toUpperCase(), latitude: null, longitude: null, radius_miles: null };
    }
    throw new Error(`${label} must use GA, Atlanta, GA, Fulton County, GA, or a five-digit ZIP — one per line.`);
  });
}

function CheckboxGroup({
  initial,
  label,
  name,
  options,
}: {
  initial: string[];
  label: string;
  name: string;
  options: string[];
}) {
  return (
    <fieldset className={styles.choiceGroup}>
      <legend>{label}</legend>
      <div>{options.map((option) => <label key={option}><input defaultChecked={initial.includes(option)} name={name} type="checkbox" value={option} /><span>{labelize(option)}</span></label>)}</div>
    </fieldset>
  );
}

export function BuyerBuyBoxForm({
  asset,
  buyerId,
  current,
  onCancel,
  onSaved,
}: {
  asset: BuyerBuyBoxAsset;
  buyerId: string;
  current?: BuyerBuyBoxSummary | null;
  onCancel: () => void;
  onSaved: (version: BuyerBuyBoxVersion) => void;
}) {
  const { getToken } = useAuth();
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const apiBaseUrl = useMemo(() => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000", []);
  const criteria = current?.criteria;
  const base = criteria?.asset_class === asset ? criteria : null;
  const radius = radiusGeography(base?.geographies ?? []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "saving") return;
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const minPrice = optionalCents(form, "min_price");
      const maxPrice = optionalCents(form, "max_price");
      const capital = optionalCents(form, "available_capital");
      const maxConcurrent = optionalInteger(form, "max_concurrent_purchases");
      const monthlyTarget = optionalInteger(form, "target_purchases_per_month");
      const numericValues = [minPrice, maxPrice, capital, maxConcurrent, monthlyTarget];
      if (numericValues.some((value) => value !== null && (!Number.isFinite(value) || value < 0))) {
        throw new Error("Prices and capacity must be non-negative numbers.");
      }
      if (minPrice !== null && maxPrice !== null && minPrice > maxPrice) {
        throw new Error("Minimum purchase price cannot be higher than the maximum.");
      }
      const geographies = parseGeographies(text(form, "geographies"), "Coverage");
      const radiusLabel = text(form, "radius_label");
      const latitude = optionalNumber(form, "radius_latitude");
      const longitude = optionalNumber(form, "radius_longitude");
      const radiusMiles = optionalNumber(form, "radius_miles");
      if ([radiusLabel, latitude, longitude, radiusMiles].some((value) => value !== "" && value !== null)) {
        if (!radiusLabel || latitude === null || longitude === null || radiusMiles === null || [latitude, longitude, radiusMiles].some((value) => !Number.isFinite(value))) {
          throw new Error("Radius coverage needs a center label, latitude, longitude, and miles.");
        }
        if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180 || radiusMiles <= 0 || radiusMiles > 500) {
          throw new Error("Radius coverage needs valid coordinates and a radius between 0.1 and 500 miles.");
        }
        geographies.push({ jurisdiction: "radius", value: radiusLabel, state: null, latitude, longitude, radius_miles: radiusMiles });
      }
      const common = {
        asset_class: asset,
        geographies,
        excluded_geographies: parseGeographies(text(form, "excluded_geographies"), "Excluded coverage"),
        strategies: checked(form, "strategies"),
        min_price_cents: minPrice,
        max_price_cents: maxPrice,
        funding_methods: checked(form, "funding_methods"),
        capacity: {
          available_capital_cents: capital,
          max_concurrent_purchases: maxConcurrent,
          target_purchases_per_month: monthlyTarget,
        },
        exclusions: listLines(text(form, "exclusions")),
      };
      let nextCriteria: BuyerBuyBoxCriteria;
      if (asset === "house") {
        const rangeValues = [
          optionalNumber(form, "min_bedrooms"), optionalNumber(form, "max_bedrooms"),
          optionalNumber(form, "min_bathrooms"), optionalNumber(form, "max_bathrooms"),
          optionalInteger(form, "min_living_area_sqft"), optionalInteger(form, "max_living_area_sqft"),
          optionalInteger(form, "min_year_built"), optionalInteger(form, "max_year_built"),
        ];
        if (rangeValues.some((value) => value !== null && (!Number.isFinite(value) || value < 0))) throw new Error("House ranges must use non-negative numbers.");
        requireOrderedRange(rangeValues[0], rangeValues[1], "bedroom count");
        requireOrderedRange(rangeValues[2], rangeValues[3], "bathroom count");
        requireOrderedRange(rangeValues[4], rangeValues[5], "living area");
        requireOrderedRange(rangeValues[6], rangeValues[7], "year built");
        nextCriteria = {
          ...common,
          asset_class: "house",
          property_types: checked(form, "property_types"),
          rehab_tolerance: checked(form, "rehab_tolerance"),
          occupancy_preferences: checked(form, "occupancy_preferences"),
          min_bedrooms: rangeValues[0], max_bedrooms: rangeValues[1],
          min_bathrooms: rangeValues[2], max_bathrooms: rangeValues[3],
          min_living_area_sqft: rangeValues[4], max_living_area_sqft: rangeValues[5],
          min_year_built: rangeValues[6], max_year_built: rangeValues[7],
        };
      } else {
        const minAcres = optionalNumber(form, "min_acres");
        const maxAcres = optionalNumber(form, "max_acres");
        if ([minAcres, maxAcres].some((value) => value !== null && (!Number.isFinite(value) || value < 0))) throw new Error("Acreage must use non-negative numbers.");
        if (minAcres !== null && maxAcres !== null && minAcres > maxAcres) throw new Error("Minimum acreage cannot be higher than maximum acreage.");
        nextCriteria = {
          ...common,
          asset_class: "land",
          min_acres: minAcres,
          max_acres: maxAcres,
          intended_uses: checked(form, "intended_uses"),
          zoning_codes: text(form, "zoning_codes").split(",").map((value) => value.trim()).filter(Boolean),
          access_preferences: checked(form, "access_preferences"),
          utility_preferences: checked(form, "utility_preferences"),
          terrain_preferences: checked(form, "terrain_preferences"),
          flood_zone_tolerance: text(form, "flood_zone_tolerance") as "avoid" | "review" | "accepted",
          wetlands_tolerance: text(form, "wetlands_tolerance") as "avoid" | "review" | "accepted",
        };
      }
      const verificationStatus = text(form, "verification_status") || "unverified";
      if (verificationStatus === "verified") {
        if (!geographies.length) {
          throw new Error("A verified buy box needs at least one included location.");
        }
        if (minPrice === null && maxPrice === null) {
          throw new Error("A verified buy box needs a minimum or maximum purchase price.");
        }
        if (asset === "house" && nextCriteria.asset_class === "house" && !nextCriteria.property_types.length) {
          throw new Error("A verified House buy box needs at least one property type.");
        }
      }
      setStatus("saving");
      const token = await getToken().catch(() => null);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      else headers["X-Dev-User-Email"] = process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";
      const response = await fetch(`${apiBaseUrl}/api/v1/buyers/${buyerId}/buy-boxes/${asset}`, {
        method: "PUT",
        headers,
        body: JSON.stringify({
          expected_version: current?.current_version ?? 0,
          source: "buyer_profile",
          change_reason: text(form, "change_reason"),
          verification_status: verificationStatus,
          criteria: nextCriteria,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as {
          detail?: string | { message?: string; code?: string } | Array<{ msg?: string }>;
        } | null;
        if (response.status === 409) throw new Error("This buy box changed in another session. Close this editor, refresh the buyer, and apply your changes to the latest version.");
        const detail = payload?.detail;
        if (Array.isArray(detail)) {
          const messages = detail.map((item) => item.msg).filter(Boolean).join(" ");
          throw new Error(messages || `Stonegate could not save this buy box (HTTP ${response.status}).`);
        }
        throw new Error(typeof detail === "string" ? detail : detail?.message ?? `Stonegate could not save this buy box (HTTP ${response.status}).`);
      }
      onSaved(await response.json() as BuyerBuyBoxVersion);
      setStatus("idle");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Stonegate could not save this buy box.");
      setStatus("error");
    }
  }

  const house = base?.asset_class === "house" ? base : null;
  const land = base?.asset_class === "land" ? base : null;

  return (
    <form className={styles.buyBoxForm} onSubmit={submit}>
      <div className={styles.formIntro}><strong>{asset === "house" ? "House buy box" : "Land buy box"} · Version {current?.current_version ?? 0}</strong><p>This creates a new immutable version. House and Land rules remain independent.</p></div>

      <section className={styles.formSection}><header><span>Geography</span><h3>Where this buyer purchases</h3></header>
        <label><span>Coverage</span><textarea defaultValue={geographyLines(base?.geographies ?? [])} name="geographies" placeholder={"GA\nAtlanta, GA\nFulton County, GA\n30303"} rows={4} /><small>One state, city and state, county and state, or ZIP per line.</small></label>
        <div className={styles.formGridThree}><label><span>Radius center</span><input defaultValue={radius?.value ?? ""} name="radius_label" placeholder="Atlanta, GA" /></label><label><span>Latitude</span><input defaultValue={radius?.latitude ?? ""} max="90" min="-90" name="radius_latitude" step="any" type="number" /></label><label><span>Longitude</span><input defaultValue={radius?.longitude ?? ""} max="180" min="-180" name="radius_longitude" step="any" type="number" /></label></div>
        <label><span>Radius miles</span><input defaultValue={radius?.radius_miles ?? ""} max="500" min="0.1" name="radius_miles" step="0.1" type="number" /></label>
        <label><span>Excluded locations</span><textarea defaultValue={geographyLines(base?.excluded_geographies ?? [])} name="excluded_geographies" placeholder={"Fulton County, GA\n30303"} rows={3} /><small>Exclusions always override covered locations.</small></label>
      </section>

      <section className={styles.formSection}><header><span>Economics</span><h3>Price, funding, and capacity</h3></header>
        <div className={styles.formGridThree}><label><span>Minimum price</span><input defaultValue={dollars(base?.min_price_cents)} min="0" name="min_price" step="1" type="number" /></label><label><span>Maximum price</span><input defaultValue={dollars(base?.max_price_cents)} min="0" name="max_price" step="1" type="number" /></label><label><span>Available capital</span><input defaultValue={dollars(base?.capacity.available_capital_cents)} min="0" name="available_capital" step="1" type="number" /></label></div>
        <div className={styles.formGridThree}><label><span>Max simultaneous purchases</span><input defaultValue={base?.capacity.max_concurrent_purchases ?? ""} min="0" name="max_concurrent_purchases" step="1" type="number" /></label><label><span>Target purchases / month</span><input defaultValue={base?.capacity.target_purchases_per_month ?? ""} min="0" name="target_purchases_per_month" step="1" type="number" /></label></div>
        <CheckboxGroup initial={base?.funding_methods ?? []} label="Funding methods" name="funding_methods" options={fundingMethods} />
        <CheckboxGroup initial={base?.strategies ?? []} label="Strategies" name="strategies" options={strategies} />
      </section>

      {asset === "house" ? <section className={styles.formSection}><header><span>House rules</span><h3>Property fit</h3></header>
        <CheckboxGroup initial={house?.property_types ?? []} label="Property types" name="property_types" options={housePropertyTypes} />
        <CheckboxGroup initial={house?.rehab_tolerance ?? []} label="Rehab tolerance" name="rehab_tolerance" options={rehabLevels} />
        <CheckboxGroup initial={house?.occupancy_preferences ?? []} label="Occupancy" name="occupancy_preferences" options={occupancies} />
        <div className={styles.formGridFour}><label><span>Min beds</span><input defaultValue={house?.min_bedrooms ?? ""} max="100" min="0" name="min_bedrooms" step="1" type="number" /></label><label><span>Max beds</span><input defaultValue={house?.max_bedrooms ?? ""} max="100" min="0" name="max_bedrooms" step="1" type="number" /></label><label><span>Min baths</span><input defaultValue={house?.min_bathrooms ?? ""} max="100" min="0" name="min_bathrooms" step="0.5" type="number" /></label><label><span>Max baths</span><input defaultValue={house?.max_bathrooms ?? ""} max="100" min="0" name="max_bathrooms" step="0.5" type="number" /></label></div>
        <div className={styles.formGridFour}><label><span>Min sqft</span><input defaultValue={house?.min_living_area_sqft ?? ""} min="0" name="min_living_area_sqft" step="1" type="number" /></label><label><span>Max sqft</span><input defaultValue={house?.max_living_area_sqft ?? ""} min="0" name="max_living_area_sqft" step="1" type="number" /></label><label><span>Min year built</span><input defaultValue={house?.min_year_built ?? ""} max="2200" min="1700" name="min_year_built" step="1" type="number" /></label><label><span>Max year built</span><input defaultValue={house?.max_year_built ?? ""} max="2200" min="1700" name="max_year_built" step="1" type="number" /></label></div>
      </section> : <section className={styles.formSection}><header><span>Land rules</span><h3>Parcel fit</h3></header>
        <div className={styles.formGridThree}><label><span>Minimum acres</span><input defaultValue={land?.min_acres ?? ""} min="0" name="min_acres" step="0.01" type="number" /></label><label><span>Maximum acres</span><input defaultValue={land?.max_acres ?? ""} min="0" name="max_acres" step="0.01" type="number" /></label><label><span>Zoning codes</span><input defaultValue={land?.zoning_codes.join(", ") ?? ""} name="zoning_codes" placeholder="R-1, AG" /></label></div>
        <CheckboxGroup initial={land?.intended_uses ?? []} label="Intended uses" name="intended_uses" options={landUses} />
        <CheckboxGroup initial={land?.access_preferences ?? []} label="Access" name="access_preferences" options={accessPreferences} />
        <CheckboxGroup initial={land?.utility_preferences ?? []} label="Utilities" name="utility_preferences" options={utilityPreferences} />
        <CheckboxGroup initial={land?.terrain_preferences ?? []} label="Terrain" name="terrain_preferences" options={terrainPreferences} />
        <div className={styles.formGridThree}><label><span>Flood-zone tolerance</span><select defaultValue={land?.flood_zone_tolerance ?? "review"} name="flood_zone_tolerance"><option value="avoid">Avoid</option><option value="review">Review case by case</option><option value="accepted">Accepted</option></select></label><label><span>Wetlands tolerance</span><select defaultValue={land?.wetlands_tolerance ?? "review"} name="wetlands_tolerance"><option value="avoid">Avoid</option><option value="review">Review case by case</option><option value="accepted">Accepted</option></select></label></div>
      </section>}

      <section className={styles.formSection}><header><span>Controls</span><h3>Exclusions and version evidence</h3></header>
        <label><span>Other hard exclusions</span><textarea defaultValue={base?.exclusions.join("\n") ?? ""} name="exclusions" placeholder={asset === "house" ? "No fire damage\nNo HOA litigation" : "No landlocked parcels\nNo conservation easements"} rows={3} /><small>One exclusion per line. These override positive preferences.</small></label>
        <label><span>Verification status</span><select defaultValue={current?.verification_status ?? "unverified"} name="verification_status"><option value="unverified">Unverified</option><option value="needs_review">Needs review</option><option value="verified">Verified with buyer</option><option value="rejected">Rejected / unusable</option></select></label>
        <label><span>Why is this version changing?</span><textarea defaultValue={current ? "Updated after buyer review" : "Initial structured buy box"} maxLength={500} minLength={2} name="change_reason" required rows={2} /></label>
      </section>

      {asset === "land" ? <p className={styles.infoNotice}>Land criteria are used by the asset-aware buyer pool. Residential outreach, Offer Room, and provider automation remain unavailable for Land.</p> : null}
      {error ? <p className={styles.formError} role="alert">{error}</p> : null}
      <div className={`${styles.formActions} ${styles.stickyActions}`}><button className={styles.secondaryAction} onClick={onCancel} type="button">Cancel</button><button disabled={status === "saving"} type="submit">{status === "saving" ? "Saving version..." : `Save ${asset} buy box`}</button></div>
    </form>
  );
}
