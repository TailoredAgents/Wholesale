import type { MetadataRoute } from "next";

import { sellerSituations } from "./seller-situations";
import { serviceAreas } from "./service-areas";
import { siteConfig } from "./site-config";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "",
    "/how-it-works",
    "/about",
    "/faqs",
    "/contact",
    "/get-a-cash-offer",
    "/privacy-policy",
    "/terms",
  ];
  const localRoutes = serviceAreas.map((area) => `/service-areas/${area.slug}`);
  return [
    ...routes,
    ...sellerSituations.map((situation) => `/${situation.slug}`),
    ...localRoutes,
  ].map((route) => ({
    url: `${siteConfig.siteUrl}${route}`,
    changeFrequency: route === "" ? "weekly" : "monthly",
    priority:
      route === ""
        ? 1
        : route === "/get-a-cash-offer"
          ? 0.9
          : localRoutes.includes(route)
            ? 0.8
            : 0.7,
  }));
}
