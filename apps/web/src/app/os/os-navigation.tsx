import {
  BarChart3,
  Building2,
  CalendarDays,
  Handshake,
  Home,
  Inbox,
  Landmark,
  ListChecks,
  Megaphone,
  PhoneCall,
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
  allPermissions?: string[];
  activeHrefs?: string[];
  activePaths?: string[];
  alwaysVisible?: boolean;
};

export type OsNavGroup = {
  label: "Work" | "Operations" | "Business" | "Administration";
  items: OsNavItem[];
};

export const ownerRoles = ["owner", "founder_operator", "ceo"];
const acquisitionRoles = ["acquisition_manager", "acquisition_rep"];
const dispositionRoles = ["disposition_manager", "disposition_rep"];

const homeRoles = [
  "administrator",
  "operations_assistant",
  ...acquisitionRoles,
  ...dispositionRoles,
  "transaction_coordinator",
  "marketing_manager",
  "finance_accounting",
];
const workRoles = [
  "administrator",
  "operations_assistant",
  ...acquisitionRoles,
  ...dispositionRoles,
  "transaction_coordinator",
  "finance_accounting",
];

export const osNavGroups: OsNavGroup[] = [
  {
    label: "Work",
    items: [
      {
        href: "/os",
        label: "Home",
        icon: Home,
        roles: homeRoles,
        anyPermissions: [
          "leads:view",
          "leads:view_assigned",
          "deals:view",
          "financials:view",
          "operations:view",
          "communications:send_bulk",
        ],
      },
      {
        href: "/os/inbox",
        label: "Inbox",
        icon: Inbox,
        roles: workRoles,
        anyPermissions: [
          "communications:view_conversations",
          "communications:view_assigned_conversations",
        ],
      },
      {
        href: "/os/tasks",
        label: "Tasks",
        icon: ListChecks,
        roles: workRoles,
        anyPermissions: [
          "leads:view",
          "leads:view_assigned",
          "deals:view",
          "financials:view",
          "operations:view",
        ],
        activePaths: ["/os/approvals"],
      },
      {
        href: "/os/calendar",
        label: "Calendar",
        icon: CalendarDays,
        roles: workRoles,
        anyPermissions: [
          "appointments:schedule_assigned",
          "underwriting:edit",
          "deals:view",
          "financials:view",
          "operations:manage",
        ],
        activePaths: ["/os/field-operations"],
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        href: "/os/prospecting",
        label: "Prospecting",
        icon: PhoneCall,
        roles: [
          "administrator",
          "acquisition_manager",
          "operations_assistant",
          "prospecting_caller",
          "marketing_manager",
        ],
        anyPermissions: [
          "operations:manage",
          "calling_lists:work_assigned",
          "communications:send_bulk",
        ],
        activePaths: ["/os/campaigns"],
      },
      {
        href: "/os/leads",
        label: "Leads",
        icon: UsersRound,
        roles: ["administrator", "operations_assistant", ...acquisitionRoles],
        anyPermissions: ["leads:view", "leads:view_assigned"],
        activePaths: ["/os/lead-manager", "/os/pipeline", "/os/underwriting"],
      },
      {
        href: "/os/deals?view=disposition",
        label: "Dispositions",
        icon: Megaphone,
        roles: ["administrator", "operations_assistant", ...dispositionRoles],
        anyPermissions: [],
        allPermissions: ["deals:view", "buyers:view"],
        activeHrefs: [
          "/os/deals?view=disposition",
          "/os/deals?tab=disposition",
        ],
        activePaths: ["/os/dispositions"],
      },
      {
        href: "/os/deals",
        label: "Deals",
        icon: Handshake,
        roles: [
          "administrator",
          "operations_assistant",
          "acquisition_rep",
          ...dispositionRoles,
          "transaction_coordinator",
          "finance_accounting",
          "read_only_partner",
          "restricted_vendor",
        ],
        anyPermissions: ["deals:view"],
        activePaths: ["/os/transactions"],
      },
      {
        href: "/os/buyers",
        label: "Buyers",
        icon: Building2,
        roles: ["administrator", "operations_assistant", ...dispositionRoles],
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
        roles: ["finance_accounting"],
        anyPermissions: ["financials:view", "compensation:view"],
      },
      {
        href: "/os/marketing",
        label: "Marketing",
        icon: BarChart3,
        roles: ["administrator", "marketing_manager"],
        anyPermissions: [
          "financials:view",
          "communications:send_bulk",
          "marketing:manage_public_proof",
          "marketing:manage_experiments",
        ],
      },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        href: "/os/settings",
        label: "Settings",
        icon: Settings2,
        roles: ["administrator"],
        anyPermissions: [
          "users:manage",
          "operations:manage",
          "communications:manage_email_accounts",
          "communications:manage_voice_lines",
          "integrations:manage_credentials",
          "operating_model:manage",
          "ai:change_prompts",
        ],
        activePaths: ["/os/my-setup"],
      },
    ],
  },
];

export function isOwnerProfile(profile: WorkspaceProfile) {
  return profile.role_keys.some((role) => ownerRoles.includes(role));
}

export function canSeeNavItem(profile: WorkspaceProfile, item: OsNavItem) {
  if (isOwnerProfile(profile)) return true;
  if (item.alwaysVisible) return true;
  const roleRelevant = profile.role_keys.some((role) => item.roles.includes(role));
  const authorized =
    item.anyPermissions.length === 0 ||
    item.anyPermissions.some((permission) => profile.permissions.includes(permission));
  const fullyAuthorized =
    !item.allPermissions ||
    item.allPermissions.every((permission) => profile.permissions.includes(permission));
  return roleRelevant && authorized && fullyAuthorized;
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
  if (isOwnerProfile(profile) || profile.role_keys.includes("administrator")) return "/os";
  if (profile.role_keys.includes("operations_assistant")) return "/os";
  if (profile.role_keys.includes("prospecting_caller")) return "/os/prospecting?view=my-calls";
  if (profile.role_keys.includes("acquisition_manager")) return "/os/leads?view=queue";
  if (profile.role_keys.includes("acquisition_rep")) return "/os/calendar?view=day";
  if (profile.role_keys.some((role) => dispositionRoles.includes(role))) {
    return "/os/deals?view=disposition";
  }
  if (profile.role_keys.includes("transaction_coordinator")) {
    return "/os/deals?view=closing-exceptions";
  }
  if (profile.role_keys.includes("finance_accounting")) return "/os/finance";
  if (profile.role_keys.includes("marketing_manager")) return "/os/marketing";
  if (
    profile.role_keys.some((role) => ["read_only_partner", "restricted_vendor"].includes(role))
  ) {
    return "/os/deals";
  }
  return "/os";
}

function pathMatches(pathname: string, item: OsNavItem) {
  const itemPath = item.href.split("?")[0];
  if (itemPath === "/os" && pathname === "/os") return true;
  if (itemPath !== "/os" && (pathname === itemPath || pathname.startsWith(`${itemPath}/`))) {
    return true;
  }
  return item.activePaths?.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  ) ?? false;
}

function queryOwner(pathname: string, query: string) {
  if (!query) return null;
  const current = new URLSearchParams(query);
  return osNavGroups
    .flatMap((group) => group.items)
    .find((item) =>
      item.activeHrefs?.some((href) => {
        const [expectedPath, expectedQuery] = href.split("?");
        if (pathname !== expectedPath || !expectedQuery) return false;
        return Array.from(new URLSearchParams(expectedQuery).entries()).every(
          ([key, value]) => current.get(key) === value,
        );
      }),
    ) ?? null;
}

export function isNavItemActive(pathname: string, item: OsNavItem, query = "") {
  const owner = queryOwner(pathname, query);
  if (owner) return owner.href === item.href;
  return pathMatches(pathname, item);
}

export function navigationContext(pathname: string, query = "") {
  const owner = queryOwner(pathname, query);
  if (owner) {
    const group = osNavGroups.find((candidate) => candidate.items.includes(owner));
    return { group: group?.label ?? "Stonegate", label: owner.label };
  }
  for (const group of osNavGroups) {
    const item = group.items.find((candidate) => pathMatches(pathname, candidate));
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
    operations_assistant: "Operations Assistant",
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
