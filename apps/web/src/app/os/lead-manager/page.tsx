import { redirect } from "next/navigation";

export default async function LeadManagerPage({
  searchParams,
}: {
  searchParams: Promise<{ lead?: string | string[] }>;
}) {
  const params = await searchParams;
  const lead = Array.isArray(params.lead) ? params.lead[0] : params.lead;
  if (lead) redirect(`/os/leads/${encodeURIComponent(lead)}`);
  redirect("/os/leads?view=today");
}
