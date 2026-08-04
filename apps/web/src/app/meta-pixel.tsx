"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { trackMetaPixelEvent } from "./lib/conversion-events";

export function MetaPixel() {
  const pathname = usePathname();

  useEffect(() => {
    trackMetaPixelEvent("PageView");
  }, [pathname]);

  return null;
}
