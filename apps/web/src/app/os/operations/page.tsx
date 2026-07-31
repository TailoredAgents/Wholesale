import { redirect } from "next/navigation";

const destinations: Record<string, string> = {
  today: "/os/calendar",
  structure: "/os/settings/markets",
  calling: "/os/prospecting",
  team: "/os/settings/people",
  quality: "/os/settings/data-quality",
  "follow-up": "/os/settings/workflows",
};

export default async function LegacyOperationsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  redirect(destinations[tab ?? "team"] ?? "/os/settings/people");
}
