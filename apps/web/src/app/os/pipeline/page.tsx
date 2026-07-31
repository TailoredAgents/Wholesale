import { redirect } from "next/navigation";

export default async function PipelinePage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string | string[] }>;
}) {
  const params = await searchParams;
  const stage = Array.isArray(params.stage) ? params.stage[0] : params.stage;
  const query = new URLSearchParams({ display: "board" });
  if (stage) query.set("stage", stage);
  redirect(`/os/leads?${query.toString()}`);
}
