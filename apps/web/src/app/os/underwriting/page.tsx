import { redirect } from "next/navigation";

export default async function UnderwritingPage({
  searchParams,
}: {
  searchParams: Promise<{ lead?: string | string[] }>;
}) {
  const params = await searchParams;
  const lead = Array.isArray(params.lead) ? params.lead[0] : params.lead;
  const query = new URLSearchParams({ view: "underwriting" });
  if (lead) query.set("lead", lead);
  redirect(`/os/leads?${query.toString()}`);
}
