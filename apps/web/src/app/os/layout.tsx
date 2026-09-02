import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { getApprovalRequests, getWorkspaceProfileResult } from "../lib/api";
import { OsShell } from "./os-shell";

export const metadata: Metadata = {
  title: "Stonegate Operating System",
  description: "Internal acquisitions workspace for Stonegate Home Buyers.",
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
    },
  },
};

export default async function OsLayout({ children }: { children: ReactNode }) {
  const [profileResult, approvalResult] = await Promise.all([
    getWorkspaceProfileResult(),
    getApprovalRequests(),
  ]);
  const pendingApprovalCount = approvalResult.approvals.filter(
    (approval) => approval.status === "pending",
  ).length;
  return (
    <ClerkProvider>
      <Suspense fallback={null}>
        <OsShell
          initialAccessError={profileResult.errorMessage}
          initialConnectionState={profileResult.connectionState}
          pendingApprovalCount={pendingApprovalCount}
          profile={profileResult.profile}
        >
          {children}
        </OsShell>
      </Suspense>
    </ClerkProvider>
  );
}
