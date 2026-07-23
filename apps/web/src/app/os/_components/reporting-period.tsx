import Link from "next/link";

import styles from "./reporting-period.module.css";

export type ReportingPeriodKey = "30" | "90" | "all";

export function ReportingPeriod({ active, basePath }: { active: ReportingPeriodKey; basePath: string }) {
  const periods: Array<{ key: ReportingPeriodKey; label: string }> = [
    { key: "30", label: "30 days" },
    { key: "90", label: "90 days" },
    { key: "all", label: "All time" },
  ];
  return <nav aria-label="Reporting period" className={styles.period}>{periods.map((item) => <Link aria-current={active === item.key ? "page" : undefined} className={active === item.key ? styles.active : undefined} href={item.key === "all" ? basePath : `${basePath}?period=${item.key}`} key={item.key}>{item.label}</Link>)}</nav>;
}
