import { auth } from "@clerk/nextjs/server";

export type DashboardSummary = {
  total_leads: number;
  new_paid_leads: number;
  active_contracts: number;
  offers_pending: number;
  collected_revenue_cents: number;
  pipeline: Array<{ stage_key: string; count: number }>;
  source_performance: Array<{
    source: string;
    medium: string;
    campaign: string;
    page_views: number;
    form_starts: number;
    form_abandons: number;
    form_submits: number;
    call_clicks: number;
    leads_created: number;
  }>;
};

export type LeadListItem = {
  id: string;
  source: string;
  stage_key: string;
  lead_temperature: string | null;
  seller_name: string;
  preferred_name: string | null;
  property_address: string;
  property_street_address: string;
  property_city: string;
  property_state: string;
  property_postal_code: string;
  property_county: string | null;
  property_type: string | null;
  assigned_user_email: string | null;
  motivation: string | null;
  desired_timeline: string | null;
  property_condition: string | null;
  occupancy_status: string | null;
  asking_price: string | null;
  mortgage_balance: string | null;
  appointment_status: string | null;
  next_follow_up_at: string | null;
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
  open_tasks: Array<{
    id: string;
    task_type: string;
    title: string;
    status: string;
    priority: string;
    due_at: string | null;
    completed_at: string | null;
  }>;
  communications: Array<{
    id: string;
    direction: string;
    channel: string;
    status: string;
    provider: string;
    provider_message_id: string | null;
    subject: string | null;
    body: string;
    occurred_at: string;
    created_at: string;
  }>;
  appointments: Array<{
    id: string;
    appointment_type: string;
    status: string;
    scheduled_start_at: string;
    scheduled_end_at: string | null;
    location_type: string;
    location: string | null;
    notes: string | null;
    outcome: string | null;
    created_at: string;
  }>;
  underwriting_versions: Array<{
    id: string;
    version_number: number;
    status: string;
    arv_low_cents: number | null;
    arv_high_cents: number | null;
    repair_low_cents: number | null;
    repair_high_cents: number | null;
    max_offer_cents: number | null;
    recommended_offer_cents: number | null;
    offer_strategy: string | null;
    notes: string | null;
    source: string;
    created_at: string;
  }>;
  transactions: Array<{
    id: string;
    deal_id: string;
    status: string;
    contract_type: string;
    purchase_price_cents: number;
    assignment_fee_cents: number | null;
    earnest_money_cents: number | null;
    title_company: string | null;
    closing_date: string | null;
    inspection_period_days: number | null;
    contract_sent_at: string | null;
    contract_executed_at: string | null;
    notes: string | null;
    checklist_items: Array<{
      id: string;
      title: string;
      status: string;
      due_at: string | null;
      completed_at: string | null;
      sort_order: number;
    }>;
    created_at: string;
  }>;
  intelligence: {
    quality_score: number;
    urgency_score: number;
    priority_label: string;
    missing_fields: Array<{
      field_key: string;
      label: string;
      question: string;
      severity: string;
    }>;
    next_best_action: {
      action_type: string;
      label: string;
      description: string;
      priority: string;
    };
    ai_ready_summary: {
      situation: string;
      urgency: string;
      known_facts: string[];
      missing_questions: string[];
      recommended_next_action: string;
    };
  };
};

export type SpeedToLeadTask = {
  task_id: string;
  lead_id: string;
  task_type: string;
  title: string;
  seller_name: string;
  property_address: string;
  source: string;
  stage_key: string;
  priority: string;
  status: string;
  due_at: string | null;
  created_at: string;
  assigned_user_email: string | null;
  due_status: string;
};

type LeadListResponse = {
  items: LeadListItem[];
};

type SpeedToLeadQueueResponse = {
  items: SpeedToLeadTask[];
};

type TaskQueueResponse = {
  items: SpeedToLeadTask[];
};

export type DashboardData = {
  summary: DashboardSummary;
  leads: LeadListItem[];
  speedToLeadQueue: SpeedToLeadTask[];
  openTaskQueue: SpeedToLeadTask[];
  apiConnected: boolean;
};

const emptySummary: DashboardSummary = {
  total_leads: 0,
  new_paid_leads: 0,
  active_contracts: 0,
  offers_pending: 0,
  collected_revenue_cents: 0,
  pipeline: [],
  source_performance: [],
};

async function getServerApiHeaders(): Promise<Record<string, string>> {
  const token = await getClerkToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  const devUserEmail =
    process.env.DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com";
  return { "X-Dev-User-Email": devUserEmail };
}

async function getClerkToken() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return null;
  }
  try {
    const session = await auth();
    return await session.getToken();
  } catch {
    return null;
  }
}

export async function getDashboardData(): Promise<DashboardData> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const [summaryResponse, leadsResponse, speedToLeadResponse, openTaskResponse] =
      await Promise.all([
      fetch(`${apiBaseUrl}/api/v1/dashboard/summary`, {
        headers,
        cache: "no-store",
      }),
      fetch(`${apiBaseUrl}/api/v1/leads`, {
        headers,
        cache: "no-store",
      }),
      fetch(`${apiBaseUrl}/api/v1/tasks/speed-to-lead`, {
        headers,
        cache: "no-store",
      }),
      fetch(`${apiBaseUrl}/api/v1/tasks/open`, {
        headers,
        cache: "no-store",
      }),
    ]);

    if (
      !summaryResponse.ok ||
      !leadsResponse.ok ||
      !speedToLeadResponse.ok ||
      !openTaskResponse.ok
    ) {
      throw new Error("API returned a non-OK response");
    }

    const summary = (await summaryResponse.json()) as DashboardSummary;
    const leads = ((await leadsResponse.json()) as LeadListResponse).items;
    const speedToLeadQueue = ((await speedToLeadResponse.json()) as SpeedToLeadQueueResponse).items;
    const openTaskQueue = ((await openTaskResponse.json()) as TaskQueueResponse).items;
    return { summary, leads, speedToLeadQueue, openTaskQueue, apiConnected: true };
  } catch {
    return {
      summary: emptySummary,
      leads: [],
      speedToLeadQueue: [],
      openTaskQueue: [],
      apiConnected: false,
    };
  }
}

export async function getLeadDetail(leadId: string): Promise<{
  lead: LeadDetail | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/leads/${leadId}`, {
      headers,
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
