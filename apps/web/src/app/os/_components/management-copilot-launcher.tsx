"use client";

import type { ManagementCopilotOverview } from "../../lib/api";
import { CopilotLauncher } from "./copilot-launcher";
import { ManagementCopilotPanel } from "./management-copilot-panel";

export function ManagementCopilotLauncher({
  endpointBase,
  initialData,
  placement = "header",
}: {
  endpointBase: string;
  initialData: ManagementCopilotOverview;
  placement?: "header" | "inline";
}) {
  const attentionCount = initialData.readiness_gaps.length + initialData.risk_alerts.length;
  const summary =
    initialData.risk_alerts[0]?.reason ??
    initialData.readiness_gaps[0] ??
    "No material exception is currently identified.";

  return (
    <CopilotLauncher
      attentionCount={attentionCount}
      description="Evidence-backed analysis and draft recommendations. It cannot make operational changes."
      name={initialData.copilot_name}
      placement={placement}
      score={initialData.health_score}
      summary={summary}
    >
      <ManagementCopilotPanel
        endpointBase={endpointBase}
        initialData={initialData}
        layout="drawer"
      />
    </CopilotLauncher>
  );
}
