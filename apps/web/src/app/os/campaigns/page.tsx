import { redirect } from "next/navigation";

export default async function CampaignsPage() {
  redirect("/os/prospecting?view=campaigns");
}
