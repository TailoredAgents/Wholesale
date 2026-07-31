import { redirect } from "next/navigation";

type SearchValue = string | string[] | undefined;

function first(value: SearchValue) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function ApprovalsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, SearchValue>>;
}) {
  const params = (await searchParams) ?? {};
  const query = new URLSearchParams({ view: "approvals" });
  const approvalId = first(params.approval);
  if (approvalId) query.set("item", `approval:${approvalId}`);
  redirect(`/os/tasks?${query}`);
}
