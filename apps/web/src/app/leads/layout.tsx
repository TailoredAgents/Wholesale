import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";

export default function LegacyLeadLayout({ children }: { children: ReactNode }) {
  return <ClerkProvider>{children}</ClerkProvider>;
}
