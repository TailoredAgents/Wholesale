import {
  BarChart3,
  Bot,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  CheckCheck,
  ClipboardCheck,
  ContactRound,
  FileCheck2,
  Gauge,
  Handshake,
  Inbox,
  Landmark,
  ListChecks,
  Megaphone,
  PhoneCall,
  Route,
  Settings2,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import type { WorkspaceProfile } from "../lib/api";

export type OsNavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: string[];
  anyPermissions: string[];
};

export type OsNavGroup = {
  label: "Command" | "Acquisitions" | "Deal Flow" | "Business" | "Control";
  items: OsNavItem[];
};

export const ownerRoles = ["owner", "founder_operator", "ceo"];
const acquisitionRoles = ["acquisition_manager", "acquisition_rep"];
const dispositionRoles = ["disposition_manager", "disposition_rep"];

export const osNavGroups: OsNavGroup[] = [
  {
    label: "Command",
    items: [
      {
        href: "/os",
        label: "Dashboard",
        icon: Gauge,
        roles: [...ownerRoles, "administrator", ...acquisitionRoles],
        anyPermissions: ["leads:view"],
      },
      {
        href: "/os/inbox",
        label: "Inbox",
        icon: Inbox,
        roles: [...ownerRoles, ...acquisitionRoles],
        anyPermissions: ["communications:view_conversations"],
      },
      {
        href: "/os/tasks",
        label: "Work Queue",
        icon: ListChecks,
        roles: [...ownerRoles, "administrator", ...acquisitionRoles],
        anyPermissions: ["leads:view"],
      },
      {
        href: "/os/calendar",
        label: "Calendar",
        icon: CalendarDays,
        roles: [...ownerRoles, ...acquisitionRoles],
        anyPermissions: ["underwriting:edit", "operations:manage"],
      },
    ],
  },
  {
    label: "Acquisitions",
    items: [
      {
        href: "/os/operations",
        label: "Operations",
        icon: BriefcaseBusiness,
        roles: [...ownerRoles, "administrator", "acquisition_manager"],
        anyPermissions: ["operations:view"],
      },
      {
        href: "/os/campaigns",
        label: "Campaigns",
        icon: Megaphone,
        roles: [...ownerRoles, "acquisition_manager"],
        anyPermissions: ["operations:manage"],
      },
      {
        href: "/os/prospecting",
        label: "Prospecting",
        icon: PhoneCall,
        roles: [...ownerRoles, "acquisition_manager", "prospecting_caller"],
        anyPermissions: ["operations:manage", "calling_lists:work_assigned"],
      },
      {
        href: "/os/lead-manager",
        label: "Lead Desk",
        icon: ContactRound,
        roles: [...ownerRoles, ...acquisitionRoles],
        anyPermissions: ["leads:view"],
      },
      {
        href: "/os/leads",
        label: "All Leads",
        icon: UsersRound,
        roles: [...ownerRoles, "administrator", ...acquisitionRoles],
        anyPermissions: ["leads:view"],
      },
      {
        href: "/os/pipeline",
        label: "Seller Pipeline",
        icon: Route,
        roles: [...ownerRoles, "administrator", ...acquisitionRoles],
        anyPermissions: ["leads:view"],
      },
      {
        href: "/os/field-operations",
        label: "Field Operations",
        icon: ClipboardCheck,
        roles: [...ownerRoles, ...acquisitionRoles],
        anyPermissions: ["underwriting:edit", "operations:manage"],
      },
    ],
  },
  {
    label: "Deal Flow",
    items: [
      {
        href: "/os/underwriting",
        label: "Underwriting",
        icon: ChartNoAxesCombined,
        roles: [...ownerRoles, ...acquisitionRoles],
        anyPermissions: ["underwriting:edit"],
      },
      {
        href: "/os/approvals",
        label: "Approvals",
        icon: CheckCheck,
        roles: [...ownerRoles, "acquisition_manager", "transaction_coordinator"],
        anyPermissions: ["offers:approve", "contracts:send"],
      },
      {
        href: "/os/transactions",
        label: "Transactions",
        icon: FileCheck2,
        roles: [
          ...ownerRoles,
          ...acquisitionRoles,
          ...dispositionRoles,
          "transaction_coordinator",
          "read_only_partner",
          "restricted_vendor",
        ],
        anyPermissions: ["deals:view"],
      },
      {
        href: "/os/dispositions",
        label: "Dispositions",
        icon: Handshake,
        roles: [...ownerRoles, ...dispositionRoles, "transaction_coordinator"],
        anyPermissions: ["deals:view"],
      },
      {
        href: "/os/buyers",
        label: "Buyers",
        icon: Building2,
        roles: [...ownerRoles, ...dispositionRoles],
        anyPermissions: ["buyers:view"],
      },
    ],
  },
  {
    label: "Business",
    items: [
      {
        href: "/os/finance",
        label: "Finance",
        icon: Landmark,
        roles: [...ownerRoles, "finance_accounting"],
        anyPermissions: ["financials:view", "compensation:view"],
      },
      {
        href: "/os/marketing",
        label: "Marketing",
        icon: BarChart3,
        roles: [...ownerRoles, "marketing_manager"],
        anyPermissions: ["financials:view", "communications:send_bulk"],
      },
    ],
  },
  {
    label: "Control",
    items: [
      {
        href: "/os/operating-model",
        label: "Operating Model",
        icon: Settings2,
        roles: ownerRoles,
        anyPermissions: ["operating_model:manage"],
      },
      {
        href: "/os/ai",
        label: "AI Control",
        icon: Bot,
        roles: ownerRoles,
        anyPermissions: ["ai:change_prompts"],
      },
    ],
  },
];

export function isOwnerProfile(profile: WorkspaceProfile) {
  return profile.role_keys.some((role) => ownerRoles.includes(role));
}

export function canSeeNavItem(profile: WorkspaceProfile, item: OsNavItem) {
  if (isOwnerProfile(profile)) return true;
  const roleRelevant = profile.role_keys.some((role) => item.roles.includes(role));
  const authorized = item.anyPermissions.some((permission) =>
    profile.permissions.includes(permission),
  );
  return roleRelevant && authorized;
}

export function visibleNavGroups(profile: WorkspaceProfile) {
  return osNavGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => canSeeNavItem(profile, item)),
    }))
    .filter((group) => group.items.length > 0);
}

export function defaultRouteForProfile(profile: WorkspaceProfile) {
  if (profile.role_keys.includes("prospecting_caller")) return "/os/prospecting";
  if (profile.role_keys.some((role) => dispositionRoles.includes(role))) return "/os/dispositions";
  if (profile.role_keys.includes("transaction_coordinator")) return "/os/transactions";
  if (profile.role_keys.includes("finance_accounting")) return "/os/finance";
  if (profile.role_keys.includes("marketing_manager")) return "/os/marketing";
  if (
    profile.role_keys.some((role) => ["read_only_partner", "restricted_vendor"].includes(role))
  ) {
    return "/os/transactions";
  }
  return "/os";
}

export function navigationContext(pathname: string) {
  if (pathname === "/os/leads/archived") {
    return { group: "Acquisitions", label: "Archived Leads" };
  }
  if (/^\/os\/leads\/[^/]+$/.test(pathname)) {
    return { group: "Acquisitions", label: "Lead Record" };
  }
  for (const group of osNavGroups) {
    const item = group.items.find((candidate) =>
      candidate.href === "/os"
        ? pathname === "/os"
        : pathname === candidate.href || pathname.startsWith(`${candidate.href}/`),
    );
    if (item) return { group: group.label, label: item.label };
  }
  return { group: "Stonegate", label: "Operating System" };
}

export function primaryRoleLabel(profile: WorkspaceProfile) {
  const labels: Record<string, string> = {
    owner: "Owner",
    founder_operator: "Founder / Operator",
    ceo: "CEO",
    administrator: "Administrator",
    acquisition_manager: "Lead Manager",
    acquisition_rep: "Acquisitions Closer",
    prospecting_caller: "VA Caller",
    disposition_manager: "Dispositions Manager",
    disposition_rep: "Dispositions",
    transaction_coordinator: "Transaction Coordinator",
    marketing_manager: "Marketing Manager",
    finance_accounting: "Finance / Accounting",
    read_only_partner: "Read-only Partner",
    restricted_vendor: "Restricted Vendor",
    ai_service: "AI Service",
  };
  return profile.role_keys.map((role) => labels[role] ?? role).join(", ") || "Workspace user";
}
