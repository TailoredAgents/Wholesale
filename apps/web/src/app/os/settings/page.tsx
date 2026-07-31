import { redirect } from "next/navigation";

import { getWorkspaceProfile } from "../../lib/api";
import { visibleSettingsSections } from "./settings-sections";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await getWorkspaceProfile();
  const firstSection = visibleSettingsSections(profile)[0];
  redirect(firstSection?.href ?? "/os/my-setup");
}
