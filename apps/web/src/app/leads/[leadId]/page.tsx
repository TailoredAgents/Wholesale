import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function LegacyLeadPage({ params }: { params: Promise<{ leadId: string }> }) {
  const { leadId } = await params;
  redirect(`/os/leads/${leadId}`);
}
