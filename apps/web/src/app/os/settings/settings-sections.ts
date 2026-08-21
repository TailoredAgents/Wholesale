import type { WorkspaceProfile } from "../../lib/api";
import { isOwnerProfile } from "../os-navigation";

export type SettingsSection = {
  allowedRoles?: string[];
  description: string;
  href: string;
  key: string;
  label: string;
  permissions: string[];
};

export const settingsSections: SettingsSection[] = [
  {
    key: "company",
    label: "Company",
    href: "/os/settings/company",
    description: "Company structure, seats, partners, and role readiness.",
    permissions: ["operating_model:manage"],
  },
  {
    key: "markets",
    label: "Markets & Territories",
    href: "/os/settings/markets",
    description: "Service areas, territory ownership, and market launch readiness.",
    permissions: ["operations:manage", "operating_model:manage"],
  },
  {
    key: "people",
    label: "People & Access",
    href: "/os/settings/people",
    description: "Employee accounts, roles, teams, and workspace access.",
    permissions: ["users:manage", "operations:manage"],
  },
  {
    key: "communications",
    label: "Communications",
    href: "/os/settings/communications",
    description: "Email senders, mailbox access, reply routing, and voice administration.",
    permissions: [
      "communications:manage_email_accounts",
      "communications:manage_voice_lines",
    ],
  },
  {
    key: "integrations",
    label: "Integrations",
    href: "/os/settings/integrations",
    description: "Provider readiness and missing environment configuration.",
    permissions: ["integrations:manage_credentials"],
  },
  {
    key: "workflows",
    label: "Workflows",
    href: "/os/settings/workflows",
    description: "Approved follow-up plans and shared operating routines.",
    permissions: ["operations:manage"],
  },
  {
    key: "data-quality",
    label: "Data & Quality",
    href: "/os/settings/data-quality",
    description: "Duplicate review, record quality, and valuation calibration.",
    allowedRoles: ["administrator", "acquisition_manager", "acquisition_rep"],
    permissions: [
      "operations:manage",
      "records:delete_or_archive",
      "audit:view",
      "underwriting:edit",
      "underwriting:approve_arv",
    ],
  },
  {
    key: "finance-policy",
    label: "Finance Policy",
    href: "/os/settings/finance-policy",
    description: "Compensation rules, role credits, and policy history.",
    permissions: ["operating_model:manage", "compensation:change_rules"],
  },
  {
    key: "ai",
    label: "AI & Automation",
    href: "/os/settings/ai",
    description: "Copilot controls, evaluations, approvals, models, and cost.",
    permissions: ["ai:change_prompts"],
  },
];

export function canAccessSettingsSection(
  profile: WorkspaceProfile | null,
  section: SettingsSection,
) {
  return Boolean(
    profile &&
      (isOwnerProfile(profile) ||
        ((!section.allowedRoles ||
          section.allowedRoles.some((role) => profile.role_keys.includes(role))) &&
          section.permissions.some((permission) => profile.permissions.includes(permission)))),
  );
}

export function visibleSettingsSections(profile: WorkspaceProfile | null) {
  return settingsSections.filter((section) => canAccessSettingsSection(profile, section));
}
