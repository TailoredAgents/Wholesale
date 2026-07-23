export const siteConfig = {
  name: "Stonegate Home Buyers",
  shortName: "Stonegate",
  phoneDisplay: "(678) 541-7725",
  phoneHref: "tel:+16785417725",
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL ?? "https://stonegatehomebuyers.com",
  serviceArea: "Georgia, with an initial focus on metro Atlanta and surrounding communities",
} as const;

export const directOfferDisclosure =
  "Stonegate Home Buyers is a real estate investment company, not a brokerage or appraisal service. A direct cash offer may be below potential retail market value in exchange for an as-is sale and fewer listing steps. Any purchase remains subject to written contract terms, title review, and property verification.";

export const publicNavigation = [
  { href: "/how-it-works", label: "How It Works" },
  { href: "/#selling-situations", label: "Selling Situations" },
  { href: "/about", label: "About" },
  { href: "/faqs", label: "FAQs" },
] as const;
