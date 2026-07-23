import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  FileSearch,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import styles from "./deal-control-strip.module.css";

type Tone = "neutral" | "info" | "warning" | "danger" | "success";

export type DealControlItem = {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
};

export function DealControlStrip({
  authority,
  blocker,
  deadline,
  evidence,
  nextAction,
}: {
  authority: DealControlItem;
  blocker: DealControlItem;
  deadline: DealControlItem;
  evidence: DealControlItem;
  nextAction: DealControlItem;
}) {
  const items = [
    { ...evidence, icon: FileSearch },
    { ...authority, icon: ShieldCheck },
    { ...deadline, icon: CalendarClock },
    { ...blocker, icon: AlertTriangle },
    { ...nextAction, icon: CheckCircle2 },
  ];

  return (
    <section aria-label="Deal execution controls" className={styles.strip}>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div className={styles[item.tone ?? "neutral"]} key={item.label}>
            <Icon aria-hidden="true" size={16} />
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {item.detail ? <small>{item.detail}</small> : null}
          </div>
        );
      })}
    </section>
  );
}
