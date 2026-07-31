import {
  ArrowRight,
  BadgeCheck,
  Bot,
  BriefcaseBusiness,
  Mail,
  Settings2,
} from "lucide-react";
import Link from "next/link";

import { getWorkspaceProfile } from "../../lib/api";
import { PageHeader, WorkspacePage } from "../_components/page-contracts";
import { isOwnerProfile } from "../os-navigation";
import styles from "../_components/workspace-hub.module.css";

export const dynamic = "force-dynamic";

type SettingsLink = {
  description: string;
  href: string;
  icon: typeof Settings2;
  label: string;
  permissions?: string[];
};

const settingsLinks: SettingsLink[] = [
  {
    description: "Personal calling eligibility, assigned line, and account readiness.",
    href: "/os/my-setup",
    icon: BadgeCheck,
    label: "My Setup",
  },
  {
    description: "Employee accounts, roles, teams, access, markets, and operating controls.",
    href: "/os/operations?tab=team",
    icon: BriefcaseBusiness,
    label: "People & Access",
    permissions: ["users:manage", "operations:manage"],
  },
  {
    description: "Company sender addresses, mailbox access, reply routing, and templates.",
    href: "/os/inbox?manage=email",
    icon: Mail,
    label: "Email",
    permissions: ["communications:manage_email_accounts"],
  },
  {
    description: "Compensation rules, company policy, launch gates, and market operating plans.",
    href: "/os/operating-model",
    icon: Settings2,
    label: "Company & Policy",
    permissions: ["operating_model:manage"],
  },
  {
    description: "Copilot status, prompts, evaluations, approvals, cost, and model controls.",
    href: "/os/ai",
    icon: Bot,
    label: "AI & Automation",
    permissions: ["ai:change_prompts"],
  },
];

export default async function SettingsPage() {
  const profile = await getWorkspaceProfile();
  const owner = profile ? isOwnerProfile(profile) : false;
  const visibleLinks = settingsLinks.filter(
    (item) =>
      !item.permissions ||
      owner ||
      item.permissions.some((permission) => profile?.permissions.includes(permission)),
  );

  return (
    <WorkspacePage>
      <PageHeader
        description="Account, people, communications, company policy, and automation controls."
        eyebrow="Administration"
        meta={`${visibleLinks.length} available sections`}
        title="Settings"
      />

      <section className={styles.settingsList}>
        {visibleLinks.map((item) => (
          <Link href={item.href} key={item.href}>
            <span className={styles.settingsIcon}>
              <item.icon aria-hidden="true" size={18} />
            </span>
            <div>
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </div>
            <ArrowRight aria-hidden="true" size={17} />
          </Link>
        ))}
      </section>
    </WorkspacePage>
  );
}
