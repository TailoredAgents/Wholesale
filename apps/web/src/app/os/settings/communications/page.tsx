import { getWorkspaceProfile } from "../../../lib/api";
import { PageHeader, WorkspacePage } from "../../_components/page-contracts";
import { isOwnerProfile } from "../../os-navigation";
import { requireSettingsSection } from "../section-access";
import { EmailSettingsWorkspace } from "./email-settings-workspace";
import { VoiceLineSettings } from "./voice-line-settings";

export const dynamic = "force-dynamic";

export default async function CommunicationsSettingsPage() {
  await requireSettingsSection("communications");
  const profile = await getWorkspaceProfile();
  const owner = profile ? isOwnerProfile(profile) : false;
  const canManageEmail =
    owner || Boolean(profile?.permissions.includes("communications:manage_email_accounts"));
  const canManageVoice =
    owner || Boolean(profile?.permissions.includes("communications:manage_voice_lines"));
  return (
    <WorkspacePage>
      <PageHeader
        description="Manage company sender addresses, mailbox access, signatures, and reply routing."
        eyebrow="Settings"
        meta="Provider-safe administration"
        title="Communications"
      />
      {canManageEmail ? <EmailSettingsWorkspace /> : null}
      {canManageVoice ? <VoiceLineSettings /> : null}
    </WorkspacePage>
  );
}
