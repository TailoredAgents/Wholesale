"use client";

import { Crosshair, ExternalLink, MapPin } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

import styles from "./page.module.css";

const OPENFREEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

type PropertyLocationMapProps = {
  address: string;
  latitude: number | null;
  longitude: number | null;
};

function validCoordinates(latitude: number | null, longitude: number | null) {
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

export function PropertyLocationMap({
  address,
  latitude,
  longitude,
}: PropertyLocationMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const hasCoordinates = validCoordinates(latitude, longitude);
  const destination = hasCoordinates ? `${latitude},${longitude}` : address;
  const directionsUrl = useMemo(
    () => `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}`,
    [destination],
  );

  useEffect(() => {
    if (!hasCoordinates || !containerRef.current || latitude === null || longitude === null) {
      return;
    }

    let disposed = false;
    let loaded = false;
    let marker: import("maplibre-gl").Marker | null = null;

    void import("maplibre-gl")
      .then((maplibre) => {
        if (disposed || !containerRef.current) return;
        const map = new maplibre.Map({
          container: containerRef.current,
          style: OPENFREEMAP_STYLE_URL,
          center: [longitude, latitude],
          zoom: 15,
          attributionControl: false,
        });
        map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
        map.addControl(new maplibre.AttributionControl({ compact: true }), "bottom-right");
        marker = new maplibre.Marker({ color: "#2f6f4e" })
          .setLngLat([longitude, latitude])
          .setPopup(new maplibre.Popup({ offset: 24 }).setText(address))
          .addTo(map);
        map.once("load", () => {
          loaded = true;
          if (!disposed) setMapError(null);
        });
        map.on("error", () => {
          if (!disposed && !loaded) setMapError("The interactive map could not be loaded.");
        });
        mapRef.current = map;
      })
      .catch(() => {
        if (!disposed) setMapError("The interactive map could not be loaded.");
      });

    return () => {
      disposed = true;
      marker?.remove();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [address, hasCoordinates, latitude, longitude]);

  function recenter() {
    if (!hasCoordinates || latitude === null || longitude === null) return;
    mapRef.current?.easeTo({ center: [longitude, latitude], zoom: 15, duration: 500 });
  }

  return (
    <section className={styles.propertyLocationSection} aria-labelledby="property-location-title">
      <div className={styles.propertyLocationHeader}>
        <div>
          <span>Location</span>
          <h3 id="property-location-title">Property map</h3>
          <p>{address}</p>
        </div>
        <a href={directionsUrl} rel="noreferrer" target="_blank">
          Open directions
          <ExternalLink aria-hidden="true" size={13} />
        </a>
      </div>

      {hasCoordinates ? (
        <div className={styles.propertyMapFrame}>
          <div
            aria-label={`Interactive road map centered on ${address}`}
            className={styles.propertyMapCanvas}
            ref={containerRef}
            role="region"
          />
          <button aria-label="Recenter map on property" onClick={recenter} type="button">
            <Crosshair aria-hidden="true" size={15} />
            Recenter
          </button>
          {mapError ? <div className={styles.propertyMapError}>{mapError}</div> : null}
        </div>
      ) : (
        <div className={styles.propertyMapFallback}>
          <MapPin aria-hidden="true" size={22} />
          <div>
            <strong>Map location pending</strong>
            <span>Property research has not confirmed usable coordinates for this address.</span>
          </div>
        </div>
      )}
    </section>
  );
}
