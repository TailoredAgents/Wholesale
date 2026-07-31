import "server-only";

import { notFound } from "next/navigation";

import { getWorkspaceProfile } from "../../lib/api";
import {
  canAccessSettingsSection,
  settingsSections,
  type SettingsSection,
} from "./settings-sections";

export async function requireSettingsSection(key: string): Promise<SettingsSection> {
  const section = settingsSections.find((candidate) => candidate.key === key);
  if (!section) notFound();
  const profile = await getWorkspaceProfile();
  if (!canAccessSettingsSection(profile, section)) notFound();
  return section;
}
