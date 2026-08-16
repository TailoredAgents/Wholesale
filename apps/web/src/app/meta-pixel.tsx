"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { trackMetaPageNavigation } from "./lib/conversion-events";

export function MetaPixel() {
  const pathname = usePathname();

  useEffect(() => {
    trackMetaPageNavigation(pathname);
  }, [pathname]);

  return null;
}
