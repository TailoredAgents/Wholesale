"use client";

import { useLayoutEffect } from "react";

export function OfferPageScrollController() {
  useLayoutEffect(() => {
    const previousScrollRestoration = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";

    const resetScrollPosition = () => {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    };

    let animationFrame = 0;
    const normalizeEntryPosition = () => {
      if (window.location.hash === "#cash-offer-form") {
        window.history.replaceState(
          window.history.state,
          "",
          `${window.location.pathname}${window.location.search}`,
        );
      }

      resetScrollPosition();
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(resetScrollPosition);
    };

    const handlePageShow = (event: PageTransitionEvent) => {
      if (event.persisted) normalizeEntryPosition();
    };

    normalizeEntryPosition();
    window.addEventListener("pageshow", handlePageShow);

    return () => {
      window.removeEventListener("pageshow", handlePageShow);
      window.cancelAnimationFrame(animationFrame);
      window.history.scrollRestoration = previousScrollRestoration;
    };
  }, []);

  return null;
}
