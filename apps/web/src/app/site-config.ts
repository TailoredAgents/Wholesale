export const siteConfig = {
  name: "Stonegate Home Buyers",
  shortName: "Stonegate",
  phoneDisplay: "(678) 541-7725",
  phoneE164: "+1-678-541-7725",
  phoneHref: "tel:+16785417725",
  publicEmail: "offers@stonegatehb.com",
  publicEmailHref: "mailto:offers@stonegatehb.com",
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL ?? "https://www.stonegatehb.com",
  serviceArea: "Georgia, with an initial focus on metro Atlanta and surrounding communities",
  serviceAreaShort: "Metro Atlanta and surrounding Georgia communities",
  inquiryAvailability: "Online property requests are accepted 24 hours a day.",
} as const;

export const directOfferDisclosure =
  "Stonegate Home Buyers is a real estate investment company, not a brokerage or appraisal service. A direct cash offer may be below potential retail market value in exchange for an as-is sale and fewer listing steps. Any purchase remains subject to written contract terms, title review, and property verification.";

export const publicNavigation = [
  { href: "/how-it-works", label: "How It Works" },
  { href: "/#selling-situations", label: "Selling Situations" },
  { href: "/service-areas/metro-atlanta", label: "Service Area" },
  { href: "/about", label: "About" },
  { href: "/faqs", label: "FAQs" },
  { href: "/contact", label: "Contact" },
] as const;
