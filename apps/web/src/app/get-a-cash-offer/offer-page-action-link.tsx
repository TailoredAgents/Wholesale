"use client";

import type { ReactNode } from "react";

import { recordConversionEvent } from "../lib/conversion-events";

type OfferPageActionLinkProps = {
  className: string;
  children: ReactNode;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function OfferPageActionLink({
  className,
  children,
}: OfferPageActionLinkProps) {
  return (
    <a
      className={className}
      href="#cash-offer-form"
      onClick={() => {
        void recordConversionEvent(apiBaseUrl, "offer_start", {
          entry_point: "mobile_action_bar",
          device_context: "mobile",
          source_path: "/get-a-cash-offer",
        });
      }}
    >
      {children}
    </a>
  );
}
