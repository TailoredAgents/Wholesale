import type { MetadataRoute } from "next";

import { sellerSituations } from "./seller-situations";
import { siteConfig } from "./site-config";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = ["", "/how-it-works", "/about", "/faqs", "/get-a-cash-offer", "/privacy-policy", "/terms"];
  return [...routes, ...sellerSituations.map((situation) => `/${situation.slug}`)].map((route) => ({
    url: `${siteConfig.siteUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: route === "" ? "weekly" : "monthly",
    priority: route === "" ? 1 : route === "/get-a-cash-offer" ? 0.9 : 0.7,
  }));
}
