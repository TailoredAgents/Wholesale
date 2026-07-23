import type { MetadataRoute } from "next";

import { siteConfig } from "./site-config";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/os/", "/sign-in/", "/sign-up/"] }],
    sitemap: `${siteConfig.siteUrl}/sitemap.xml`,
  };
}
