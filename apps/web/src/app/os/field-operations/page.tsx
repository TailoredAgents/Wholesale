import { redirect } from "next/navigation";

type SearchValue = string | string[] | undefined;

function first(value: SearchValue) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function FieldOperationsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, SearchValue>>;
}) {
  const params = (await searchParams) ?? {};
  const legacyView = first(params.view);
  const view =
    legacyView === "meetings"
      ? "appointment"
      : legacyView === "capacity"
        ? "availability"
        : legacyView === "calendar"
          ? "schedule"
          : legacyView || "schedule";
  const query = new URLSearchParams();
  if (view !== "schedule") query.set("view", view);
  const appointment = first(params.appointment);
  const lead = first(params.lead);
  if (appointment) query.set("appointment", appointment);
  if (lead) query.set("lead", lead);
  const suffix = query.toString();
  redirect(suffix ? `/os/calendar?${suffix}` : "/os/calendar");
}
