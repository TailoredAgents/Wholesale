import {
  getMyComplianceTraining,
  getMyRoleSetup,
  getWorkspaceProfile,
} from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { MySetupWorkspace } from "./my-setup-workspace";

export const dynamic = "force-dynamic";

export default async function MySetupPage() {
  const [profile, { roleSetup, apiConnected }, { training }] = await Promise.all([
    getWorkspaceProfile(),
    getMyRoleSetup(),
    getMyComplianceTraining(),
  ]);

  return (
    <WorkspacePage>
      <PageHeader
        eyebrow="Account readiness"
        title="My Setup"
        description="Review your assigned role, complete the workspace test, and submit it for approval."
        meta={
          <StatusBadge tone={apiConnected ? "success" : "danger"}>
            {apiConnected ? "Connected" : "Unavailable"}
          </StatusBadge>
        }
      />
      {profile && roleSetup ? (
        <MySetupWorkspace roleSetup={roleSetup} training={training} />
      ) : (
        <p>Role setup could not be loaded.</p>
      )}
    </WorkspacePage>
  );
}
