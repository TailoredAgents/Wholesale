export const landStandardQuestions = [
  [
    "ownership_decision_makers",
    "Ownership and decision makers",
    "Who owns the parcel, how is title held, and who must agree before it can be sold?",
    true,
  ],
  ["motivation", "Reason for selling", "What has you considering selling the land now?", true],
  ["timeline", "Timeline", "When would you ideally like to complete a sale?", true],
  ["parcel_id", "Parcel / APN", "What is the parcel number or APN, if available?", false],
  ["acreage", "Acreage", "Approximately how many acres are included?", true],
  [
    "access_frontage",
    "Access and frontage",
    "What road frontage, deeded access, easements, or shared-road arrangements are known?",
    true,
  ],
  ["utilities", "Utilities", "What utilities are at the road or already connected?", false],
  [
    "survey_boundaries",
    "Survey and boundaries",
    "Is there a recent survey, and are the parcel corners or boundary lines marked?",
    false,
  ],
  [
    "zoning_use",
    "Zoning and use",
    "What zoning, current use, or permitted-use information have you been given?",
    false,
  ],
  [
    "septic_perc",
    "Septic / perc",
    "Has any soil, perc, septic, well, or sewer work been completed?",
    false,
  ],
  [
    "taxes_hoa",
    "Taxes / HOA / road fees",
    "What annual taxes, HOA or POA dues, assessments, or road fees apply?",
    false,
  ],
  [
    "restrictions",
    "Restrictions",
    "Are there recorded restrictions, covenants, easements, leases, or use limitations?",
    false,
  ],
  [
    "flood_wetlands",
    "Flood and wetlands",
    "Are you aware of mapped floodplain, wetlands, drainage, or standing-water concerns?",
    false,
  ],
  [
    "terrain_environmental",
    "Terrain and environmental",
    "Are you aware of slope, dumping, contamination, timber, or other environmental concerns?",
    false,
  ],
  [
    "prior_testing_improvements",
    "Testing and improvements",
    "What surveys, studies, permits, clearing, roads, wells, or other improvements have been completed?",
    false,
  ],
  [
    "known_concerns",
    "Known concerns",
    "What else about the parcel could affect access, use, value, or a future buyer's review?",
    false,
  ],
  [
    "title_probate_heirship",
    "Title / probate / heirs",
    "Are there title, probate, heirship, lien, or payoff issues that may affect a sale?",
    false,
  ],
  ["asking_price", "Price expectation", "Do you have a price in mind?", false],
  [
    "mortgage_balance",
    "Liens or balances",
    "Is there a mortgage, lien, tax balance, or other payoff?",
    false,
  ],
] as const;

export type LandStandardQuestion = (typeof landStandardQuestions)[number];
