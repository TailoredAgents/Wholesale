"use client";

import type { ReactNode } from "react";
import { useMemo } from "react";

import { recordConversionEvent } from "./lib/conversion-events";

type TrackedPhoneLinkProps = {
  className?: string;
  href: string;
  children: ReactNode;
};

export function TrackedPhoneLink({ className, href, children }: TrackedPhoneLinkProps) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );

  return (
    <a
      className={className}
      href={href}
      onClick={() => {
        void recordConversionEvent(apiBaseUrl, "call_click", { href });
      }}
    >
      {children}
    </a>
  );
}
