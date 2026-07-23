export type SellerSituation = {
  slug: string;
  eyebrow: string;
  shortTitle: string;
  title: string;
  description: string;
  image: string;
  imageAlt: string;
  concerns: string[];
  process: string[];
  proofPoints: string[];
};

export const sellerSituations: SellerSituation[] = [
  {
    slug: "sell-inherited-house",
    eyebrow: "Inherited property",
    shortTitle: "An inherited property",
    title: "Sell an inherited house without repairs, cleanout, or listing pressure.",
    description:
      "When a family property needs a practical next step, Stonegate can review the house as-is and help you understand a direct cash-offer option.",
    image: "/images/stonegate-inherited-home.jpg",
    imageAlt: "Older red-brick Georgia home beneath mature trees.",
    concerns: [
      "Family members are still deciding what to do",
      "The property needs cleaning, repairs, or personal items removed",
      "You want a clear option before hiring contractors or listing",
    ],
    process: [
      "Share the address and basic property details",
      "Talk through condition, timing, and ownership context",
      "Review a cash offer and choose whether it fits the situation",
    ],
    proofPoints: [
      "No showings or open houses",
      "As-is review before repair decisions",
      "Timeline can be discussed around probate and family needs",
    ],
  },
  {
    slug: "sell-house-needs-repairs",
    eyebrow: "Repairs needed",
    shortTitle: "A house that needs repairs",
    title: "Sell a house that needs repairs without managing contractors first.",
    description:
      "If repairs are blocking a traditional sale, Stonegate can evaluate the property in its current condition and make a direct offer.",
    image: "/images/stonegate-repair-kitchen.jpg",
    imageAlt: "Dated kitchen with older cabinets and flooring in need of renovation.",
    concerns: [
      "Major repairs may cost more than you want to invest",
      "Inspections could create surprise negotiation issues",
      "You want to avoid cleanup, staging, and repeated showings",
    ],
    process: [
      "Tell us what you know about the repairs",
      "We review the property, area, and likely renovation scope",
      "You get a straightforward offer without repair requirements",
    ],
    proofPoints: [
      "No contractor coordination required before requesting an offer",
      "Condition is reviewed up front",
      "Offer conversation stays focused on your net and timeline",
    ],
  },
  {
    slug: "sell-house-fast",
    eyebrow: "Fast timeline",
    shortTitle: "A sale with a tighter timeline",
    title: "Sell your house on a tighter timeline without waiting on a listing cycle.",
    description:
      "When timing matters, Stonegate gives you a direct path to compare against a traditional listing and decide what works.",
    image: "/images/stonegate-georgia-home-hero.jpg",
    imageAlt: "Red-brick Georgia home surrounded by mature trees.",
    concerns: [
      "A move, job change, or life event has a deadline",
      "You need certainty before making the next decision",
      "You want to avoid months of prep, listing, and negotiations",
    ],
    process: [
      "Request an offer with the property basics",
      "Talk with the acquisitions team about timing and condition",
      "Compare the offer against your other options before deciding",
    ],
    proofPoints: [
      "Direct review without listing prep",
      "Closing timeline can be part of the conversation",
      "No obligation to accept after requesting an offer",
    ],
  },
];

export function getSellerSituation(slug: string) {
  return sellerSituations.find((situation) => situation.slug === slug);
}
