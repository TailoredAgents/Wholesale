"use client";

import {
  Bot,
  Building2,
  Cable,
  CircleDollarSign,
  Database,
  Mail,
  Settings2,
  UsersRound,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { SettingsSection } from "./settings-sections";
import styles from "./settings.module.css";

const icons = {
  ai: Bot,
  communications: Mail,
  company: Building2,
  "data-quality": Database,
  "finance-policy": CircleDollarSign,
  integrations: Cable,
  markets: Settings2,
  people: UsersRound,
  workflows: Workflow,
};

export function SettingsNavigation({ sections }: { sections: SettingsSection[] }) {
  const pathname = usePathname();

  return (
    <aside className={styles.navigation} aria-label="Settings sections">
      <div className={styles.navigationHeading}>
        <span>Administration</span>
        <strong>Settings</strong>
      </div>
      <nav>
        {sections.map((section) => {
          const Icon = icons[section.key as keyof typeof icons] ?? Settings2;
          const active = pathname === section.href;
          return (
            <Link aria-current={active ? "page" : undefined} href={section.href} key={section.key}>
              <Icon aria-hidden="true" size={16} />
              <span>{section.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

