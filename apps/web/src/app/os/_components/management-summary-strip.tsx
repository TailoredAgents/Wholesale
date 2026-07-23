import { AlertTriangle, CalendarRange, CheckCircle2, ShieldCheck, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import styles from "./management-summary-strip.module.css";

type Tone = "neutral" | "info" | "warning" | "danger" | "success";
type Item = { label: string; value: ReactNode; detail?: ReactNode; tone?: Tone };

export function ManagementSummaryStrip({ authority, comparison, exception, nextAction, period }: { authority: Item; comparison: Item; exception: Item; nextAction: Item; period: Item }) {
  const items = [
    { ...period, icon: CalendarRange },
    { ...comparison, icon: TrendingUp },
    { ...exception, icon: AlertTriangle },
    { ...authority, icon: ShieldCheck },
    { ...nextAction, icon: CheckCircle2 },
  ];
  return <section aria-label="Management summary" className={styles.strip}>{items.map((item) => { const Icon = item.icon; return <div className={styles[item.tone ?? "neutral"]} key={item.label}><Icon aria-hidden="true" size={16} /><span>{item.label}</span><strong>{item.value}</strong>{item.detail ? <small>{item.detail}</small> : null}</div>; })}</section>;
}
