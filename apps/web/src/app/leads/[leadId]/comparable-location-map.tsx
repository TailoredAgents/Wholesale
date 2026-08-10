"use client";

import { Crosshair, MapPin } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

import type {
  CompCondition,
  CompReviewDraft,
  MarketComparable,
  SubjectProperty,
} from "./comparable-review-workbench";
import styles from "./comparable-location-map.module.css";

const OPENFREEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

type ComparableLocationMapProps = {
  comparables: MarketComparable[];
  conditionOverrides: Record<string, CompCondition>;
  requestedAddress: string;
  review: Record<string, CompReviewDraft>;
  subject: SubjectProperty;
};

type PositionedComparable = {
  comp: MarketComparable;
  key: string;
  included: boolean;
  condition: CompCondition;
  latitude: number;
  longitude: number;
};

function validCoordinates(latitude: number | null | undefined, longitude: number | null | undefined) {
  return (
    typeof latitude === "number" &&
    Number.isFinite(latitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    typeof longitude === "number" &&
    Number.isFinite(longitude) &&
    longitude >= -180 &&
    longitude <= 180
  );
}

export function ComparableLocationMap({
  comparables,
  conditionOverrides,
  requestedAddress,
  review,
  subject,
}: ComparableLocationMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const markerRefs = useRef<Map<string, import("maplibre-gl").Marker>>(new Map());
  const [mapError, setMapError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const subjectLatitude = subject.latitude;
  const subjectLongitude = subject.longitude;
  const hasSubjectCoordinates = validCoordinates(subjectLatitude, subjectLongitude);
  const positioned = useMemo(
    () =>
      comparables.flatMap((comp, index): PositionedComparable[] => {
        if (!validCoordinates(comp.latitude, comp.longitude)) return [];
        const key = comparableKey(comp, index);
        return [
          {
            comp,
            key,
            included: review[key]?.included ?? comp.selection_status !== "rejected",
            condition: conditionOverrides[key] ?? comp.condition_classification ?? "unknown",
            latitude: comp.latitude!,
            longitude: comp.longitude!,
          },
        ];
      }),
    [comparables, conditionOverrides, review],
  );

  useEffect(() => {
    if (
      !containerRef.current ||
      !hasSubjectCoordinates ||
      subjectLatitude === null ||
      subjectLatitude === undefined ||
      subjectLongitude === null ||
      subjectLongitude === undefined
    ) {
      return;
    }

    let disposed = false;
    const markers: import("maplibre-gl").Marker[] = [];
    const markerMap = markerRefs.current;

    void import("maplibre-gl")
      .then((maplibre) => {
        if (disposed || !containerRef.current) return;
        const map = new maplibre.Map({
          container: containerRef.current,
          style: OPENFREEMAP_STYLE_URL,
          center: [subjectLongitude, subjectLatitude],
          zoom: 13,
          attributionControl: false,
        });
        map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
        map.addControl(new maplibre.AttributionControl({ compact: true }), "bottom-right");

        const subjectElement = document.createElement("button");
        subjectElement.type = "button";
        subjectElement.className = `${styles.marker} ${styles.subjectMarker}`;
        subjectElement.textContent = "S";
        subjectElement.setAttribute("aria-label", `Subject property: ${requestedAddress}`);
        const subjectMarker = new maplibre.Marker({ element: subjectElement })
          .setLngLat([subjectLongitude, subjectLatitude])
          .setPopup(
            new maplibre.Popup({ offset: 18 }).setHTML(
              popupHtml("Subject property", requestedAddress, "Stonegate valuation subject"),
            ),
          )
          .addTo(map);
        markers.push(subjectMarker);

        const bounds = new maplibre.LngLatBounds(
          [subjectLongitude, subjectLatitude],
          [subjectLongitude, subjectLatitude],
        );
        positioned.forEach((item, index) => {
          const element = document.createElement("button");
          element.type = "button";
          element.className = [
            styles.marker,
            item.included ? styles.includedMarker : styles.excludedMarker,
            item.condition === "renovated"
              ? styles.renovatedMarker
              : item.condition === "as_is"
                ? styles.asIsMarker
                : "",
          ]
            .filter(Boolean)
            .join(" ");
          element.textContent = String(index + 1);
          element.setAttribute(
            "aria-label",
            `${item.included ? "Included" : "Excluded"} comparable: ${item.comp.formatted_address ?? item.key}`,
          );
          element.addEventListener("click", () => {
            if (!disposed) setSelectedKey(item.key);
          });
          const marker = new maplibre.Marker({ element })
            .setLngLat([item.longitude, item.latitude])
            .setPopup(
              new maplibre.Popup({ offset: 18 }).setHTML(
                popupHtml(
                  `${item.included ? "Included" : "Excluded"} comp`,
                  item.comp.formatted_address ?? "Unknown address",
                  `${formatDistance(item.comp.distance_miles)} · Grade ${item.comp.comp_grade ?? "--"} · ${conditionLabel(item.condition)}`,
                ),
              ),
            )
            .addTo(map);
          markerMap.set(item.key, marker);
          markers.push(marker);
          bounds.extend([item.longitude, item.latitude]);
        });

        map.once("load", () => {
          if (disposed) return;
          setMapError(null);
          if (positioned.length) {
            map.fitBounds(bounds, { padding: 58, maxZoom: 15, duration: 0 });
          }
        });
        map.on("error", () => {
          if (!disposed && !map.loaded()) {
            setMapError("The interactive comparable map could not be loaded.");
          }
        });
        mapRef.current = map;
      })
      .catch(() => {
        if (!disposed) setMapError("The interactive comparable map could not be loaded.");
      });

    return () => {
      disposed = true;
      markers.forEach((marker) => marker.remove());
      markerMap.clear();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [
    hasSubjectCoordinates,
    positioned,
    requestedAddress,
    subjectLatitude,
    subjectLongitude,
  ]);

  function recenter() {
    if (!mapRef.current || !hasSubjectCoordinates) return;
    const allCoordinates: [number, number][] = [
      [subjectLongitude!, subjectLatitude!],
      ...positioned.map((item): [number, number] => [item.longitude, item.latitude]),
    ];
    if (allCoordinates.length === 1) {
      mapRef.current.easeTo({ center: allCoordinates[0], zoom: 14, duration: 450 });
      return;
    }
    void import("maplibre-gl").then((maplibre) => {
      const bounds = allCoordinates.reduce(
        (current, coordinate) => current.extend(coordinate),
        new maplibre.LngLatBounds(allCoordinates[0], allCoordinates[0]),
      );
      mapRef.current?.fitBounds(bounds, { padding: 58, maxZoom: 15, duration: 450 });
    });
  }

  function focusComparable(item: PositionedComparable) {
    setSelectedKey(item.key);
    mapRef.current?.flyTo({ center: [item.longitude, item.latitude], zoom: 15, duration: 500 });
    markerRefs.current.get(item.key)?.togglePopup();
  }

  if (!hasSubjectCoordinates) {
    return (
      <div className={styles.fallback}>
        <MapPin aria-hidden="true" size={22} />
        <div>
          <strong>Comparable map pending</strong>
          <span>The saved subject analysis does not contain usable coordinates.</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.layout}>
      <div className={styles.mapFrame}>
        <div
          aria-label={`Interactive comparable-sale map for ${requestedAddress}`}
          className={styles.mapCanvas}
          ref={containerRef}
          role="region"
        />
        <button className={styles.recenter} onClick={recenter} type="button">
          <Crosshair aria-hidden="true" size={14} />
          Fit properties
        </button>
        <div className={styles.mapLegend}>
          <span data-kind="subject">Subject</span>
          <span data-kind="included">Included</span>
          <span data-kind="excluded">Excluded</span>
        </div>
        {mapError ? <div className={styles.mapError}>{mapError}</div> : null}
      </div>

      <aside className={styles.list} aria-label="Mapped comparable sales">
        <header>
          <strong>{positioned.length} mapped sales</strong>
          <span>{comparables.length - positioned.length} without coordinates</span>
        </header>
        {positioned.map((item, index) => (
          <button
            aria-pressed={selectedKey === item.key}
            data-included={item.included}
            key={item.key}
            onClick={() => focusComparable(item)}
            type="button"
          >
            <span>{index + 1}</span>
            <div>
              <strong>{item.comp.formatted_address ?? "Unknown address"}</strong>
              <small>
                {formatDistance(item.comp.distance_miles)} · Grade {item.comp.comp_grade ?? "--"} ·{" "}
                {conditionLabel(item.condition)}
              </small>
            </div>
          </button>
        ))}
        {!positioned.length ? (
          <p>No comparable coordinates are available in this saved analysis.</p>
        ) : null}
      </aside>
    </div>
  );
}

function popupHtml(title: string, address: string, detail: string) {
  return `<strong>${escapeHtml(title)}</strong><br/><span>${escapeHtml(address)}</span><br/><small>${escapeHtml(detail)}</small>`;
}

function escapeHtml(value: string) {
  return value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        character
      ] ?? character,
  );
}

function comparableKey(comp: MarketComparable, index: number) {
  return comp.provider_id ?? comp.formatted_address ?? `comp-${index}`;
}

function conditionLabel(value: CompCondition) {
  if (value === "renovated") return "Renovated";
  if (value === "as_is") return "As-is";
  return "Condition unknown";
}

function formatDistance(value: number | null | undefined) {
  return typeof value === "number" ? `${value.toFixed(2)} mi` : "Distance unknown";
}
