"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <main
          style={{
            alignItems: "center",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
            justifyContent: "center",
            minHeight: "100vh",
            padding: "32px",
            textAlign: "center",
          }}
        >
          <p style={{ color: "#35624b", fontWeight: 700, margin: 0 }}>Stonegate Home Buyers</p>
          <h1 style={{ fontSize: "32px", margin: 0 }}>This page could not be loaded.</h1>
          <p style={{ color: "#4e5b54", margin: 0 }}>
            The error was recorded. Please try the request again.
          </p>
          <button
            onClick={reset}
            style={{
              background: "#286a49",
              border: 0,
              borderRadius: "6px",
              color: "#ffffff",
              cursor: "pointer",
              fontWeight: 700,
              padding: "12px 18px",
            }}
            type="button"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}

