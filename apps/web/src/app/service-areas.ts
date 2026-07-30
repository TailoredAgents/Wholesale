export type ServiceArea = {
  slug: string;
  name: string;
  eyebrow: string;
  title: string;
  description: string;
  image: string;
  imageAlt: string;
  coverageNotes: string[];
  reviewFactors: string[];
  faqs: Array<{
    question: string;
    answer: string;
  }>;
};

export const serviceAreas: ServiceArea[] = [
  {
    slug: "metro-atlanta",
    name: "Metro Atlanta",
    eyebrow: "Metro Atlanta service area",
    title: "A direct home-sale option for Metro Atlanta property owners.",
    description:
      "Stonegate begins with the property address, confirms that the team can responsibly evaluate the location, and then explains whether a direct as-is offer may fit.",
    image: "/images/stonegate-georgia-home-hero.jpg",
    imageAlt: "Red-brick Metro Atlanta area home surrounded by mature trees",
    coverageNotes: [
      "Metro Atlanta is Stonegate's initial operating focus.",
      "Coverage is confirmed from the exact property address, not assumed from a broad regional label.",
      "Properties outside the immediate area may still be submitted for an honest coverage check.",
    ],
    reviewFactors: [
      "The property's location, type, size, age, and current condition",
      "Recent nearby sales and current local buyer demand",
      "Likely repairs, resale costs, access, title, and transaction risk",
      "The seller's timing and whether an as-is direct sale solves the actual problem",
    ],
    faqs: [
      {
        question: "Do I need to be inside Atlanta city limits?",
        answer:
          "No. Metro Atlanta includes communities beyond the City of Atlanta. Stonegate confirms coverage using the complete property address before asking you to rely on the process.",
      },
      {
        question: "Does Stonegate buy every property in the service area?",
        answer:
          "No. Location is only one part of the review. Property condition, title, access, price expectations, local demand, and current team capacity can all affect whether Stonegate can make an offer.",
      },
      {
        question: "Will someone need to visit the property?",
        answer:
          "A property visit may be helpful before a final decision or contract. Stonegate confirms the next step with you first and schedules property meetings by appointment.",
      },
      {
        question: "How does location affect the offer?",
        answer:
          "Location affects comparable sales, resale demand, holding risk, repair economics, and the likely buyer pool. Stonegate reviews those factors with the property's condition and transaction details rather than using location alone.",
      },
    ],
  },
];

export function findServiceArea(slug: string) {
  return serviceAreas.find((area) => area.slug === slug);
}
