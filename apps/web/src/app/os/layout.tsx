import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { getApprovalRequests, getWorkspaceProfile } from "../lib/api";
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
  const [profile, approvalResult] = await Promise.all([
    getWorkspaceProfile(),
    getApprovalRequests(),
  ]);
  const pendingApprovalCount = approvalResult.approvals.filter(
    (approval) => approval.status === "pending",
  ).length;
  return (
    <Suspense fallback={null}>
      <OsShell pendingApprovalCount={pendingApprovalCount} profile={profile}>
        {children}
      </OsShell>
    </Suspense>
  );
}
