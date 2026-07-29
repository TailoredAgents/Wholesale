import type { Metadata } from "next";
import type { ReactNode } from "react";

import { getWorkspaceProfile } from "../lib/api";
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
  const profile = await getWorkspaceProfile();
  return <OsShell profile={profile}>{children}</OsShell>;
}
