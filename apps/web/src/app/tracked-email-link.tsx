"use client";

import type { ReactNode } from "react";
import { useMemo } from "react";

import { recordConversionEvent } from "./lib/conversion-events";

type TrackedEmailLinkProps = {
  className?: string;
  href: string;
  metadata?: Record<string, unknown>;
  children: ReactNode;
};

export function TrackedEmailLink({
  className,
  href,
  metadata,
  children,
}: TrackedEmailLinkProps) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );

  return (
    <a
      className={className}
      href={href}
      onClick={() => {
        void recordConversionEvent(apiBaseUrl, "email_click", { href, ...metadata });
      }}
    >
      {children}
    </a>
  );
}
