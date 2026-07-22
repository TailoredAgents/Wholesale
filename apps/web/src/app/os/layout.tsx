import type { ReactNode } from "react";

import { getWorkspaceProfile } from "../lib/api";
import { OsShell } from "./os-shell";

export const metadata = {
  title: "Stonegate Operating System",
  description: "Internal acquisitions workspace for Stonegate Home Buyers.",
};

export default async function OsLayout({ children }: { children: ReactNode }) {
  const profile = await getWorkspaceProfile();
  return <OsShell profile={profile}>{children}</OsShell>;
}
