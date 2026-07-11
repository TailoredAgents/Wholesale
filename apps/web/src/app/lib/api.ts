export type DashboardSummary = {
  total_leads: number;
  new_paid_leads: number;
  active_contracts: number;
  offers_pending: number;
  collected_revenue_cents: number;
  pipeline: Array<{ stage_key: string; count: number }>;
};

export type LeadListItem = {
  id: string;
  source: string;
  stage_key: string;
  lead_temperature: string | null;
  seller_name: string;
  property_address: string;
  assigned_user_email: string | null;
  created_at: string;
};

export type LeadDetail = LeadListItem & {
  contact_methods: Array<{
    method_type: string;
    value: string;
    is_primary: boolean;
  }>;
  consent_records: Array<{
    channel: string;
    status: string;
    source: string;
    wording_version: string;
    captured_ip: string | null;
    created_at: string;
  }>;
  attribution_touches: Array<{
    touch_type: string;
    source: string | null;
    medium: string | null;
    campaign: string | null;
    term: string | null;
    content: string | null;
    gclid: string | null;
    fbclid: string | null;
    landing_page: string | null;
    referrer: string | null;
    created_at: string;
  }>;
  recent_activity: Array<{
    event_type: string;
    summary: string;
    created_at: string;
  }>;
};

type LeadListResponse = {
  items: LeadListItem[];
};

export type DashboardData = {
  summary: DashboardSummary;
  leads: LeadListItem[];
  apiConnected: boolean;
};

const emptySummary: DashboardSummary = {
  total_leads: 0,
  new_paid_leads: 0,
  active_contracts: 0,
  offers_pending: 0,
  collected_revenue_cents: 0,
  pipeline: [],
};

export async function getDashboardData(): Promise<DashboardData> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const devUserEmail =
    process.env.DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";

  try {
    const headers = { "X-Dev-User-Email": devUserEmail };
    const [summaryResponse, leadsResponse] = await Promise.all([
      fetch(`${apiBaseUrl}/api/v1/dashboard/summary`, {
        headers,
        cache: "no-store",
      }),
      fetch(`${apiBaseUrl}/api/v1/leads`, {
        headers,
        cache: "no-store",
      }),
    ]);

    if (!summaryResponse.ok || !leadsResponse.ok) {
      throw new Error("API returned a non-OK response");
    }

    const summary = (await summaryResponse.json()) as DashboardSummary;
    const leads = ((await leadsResponse.json()) as LeadListResponse).items;
    return { summary, leads, apiConnected: true };
  } catch {
    return { summary: emptySummary, leads: [], apiConnected: false };
  }
}

export async function getLeadDetail(leadId: string): Promise<{
  lead: LeadDetail | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const devUserEmail =
    process.env.DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";

  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}`, {
      headers: { "X-Dev-User-Email": devUserEmail },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("API returned a non-OK response");
    }

    return { lead: (await response.json()) as LeadDetail, apiConnected: true };
  } catch {
    return { lead: null, apiConnected: false };
  }
}
