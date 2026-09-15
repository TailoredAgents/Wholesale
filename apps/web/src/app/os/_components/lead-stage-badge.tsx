import { getPipelineStage, labelize } from "../os-utils";

import styles from "./lead-stage-badge.module.css";

type StageFamily =
  | "new"
  | "contacting"
  | "contacted"
  | "qualifying"
  | "qualified"
  | "appointment"
  | "underwriting"
  | "offer"
  | "nurture"
  | "under_contract"
  | "closed"
  | "other";

function stageFamily(stageKey: string): StageFamily {
  const pipelineStage = getPipelineStage(stageKey)?.key;
  if (pipelineStage) return pipelineStage;
  if (["dead", "disqualified", "closed"].includes(stageKey)) return "closed";
  return "other";
}

export function LeadStageBadge({ stageKey }: { stageKey: string }) {
  const label = getPipelineStage(stageKey)?.label ?? labelize(stageKey);

  return (
    <span className={styles.badge} data-stage={stageFamily(stageKey)}>
      {label}
    </span>
  );
}
