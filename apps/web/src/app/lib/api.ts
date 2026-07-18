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
  archived_at: string | null;
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
  buyer_offers: Array<{
    id: string;
    buyer_id: string;
    buyer_name: string;
    amount_cents: number;
    earnest_money_cents: number | null;
    financing_type: string;
    status: string;
    proof_of_funds_received: boolean;
    notes: string | null;
    received_at: string;
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

export type BuyerListItem = {
  id: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  buyer_type: string;
  status: string;
  proof_of_funds_status: string;
  max_purchase_price_cents: number | null;
  notes: string | null;
  criteria: {
    markets: string | null;
    property_types: string | null;
    min_price_cents: number | null;
    max_price_cents: number | null;
    rehab_levels: string | null;
    notes: string | null;
  } | null;
  created_at: string;
};

export type FinanceOverview = {
  summary: {
    collected_revenue_cents: number;
    pending_revenue_cents: number;
    deductions_cents: number;
    net_revenue_cents: number;
    compensation_cents: number;
    marketing_spend_cents: number;
    company_net_cents: number;
  };
  revenue_records: Array<{
    id: string;
    lead_id: string | null;
    deal_id: string | null;
    transaction_id: string | null;
    seller_name: string | null;
    property_address: string | null;
    source: string;
    status: string;
    amount_cents: number;
    received_at: string;
    notes: string | null;
    created_at: string;
  }>;
  deductions: Array<{
    id: string;
    lead_id: string | null;
    deal_id: string | null;
    transaction_id: string | null;
    category: string;
    amount_cents: number;
    incurred_at: string;
    notes: string | null;
    created_at: string;
  }>;
  compensation_rules: Array<{
    id: string;
    name: string;
    role_key: string;
    basis_points: number;
    applies_to: string;
    effective_start_at: string;
    effective_end_at: string | null;
    is_active: boolean;
    notes: string | null;
    created_at: string;
  }>;
  compensation_calculations: Array<{
    id: string;
    revenue_record_id: string;
    compensation_rule_id: string;
    role_key: string;
    basis_amount_cents: number;
    basis_points: number;
    calculated_amount_cents: number;
    status: string;
    notes: string | null;
    created_at: string;
  }>;
  marketing_spend: Array<{
    id: string;
    source: string;
    campaign: string | null;
    amount_cents: number;
    spend_month_at: string;
    notes: string | null;
    created_at: string;
  }>;
};

export type MarketingOverview = {
  summary: {
    total_spend_cents: number;
    collected_revenue_cents: number;
    leads_created: number;
    contracted_leads: number;
    cost_per_lead_cents: number | null;
    cost_per_contract_cents: number | null;
    return_on_ad_spend_basis_points: number | null;
    pending_offline_exports: number;
  };
  campaigns: Array<{
    source: string;
    medium: string;
    campaign: string;
    page_views: number;
    form_starts: number;
    form_abandons: number;
    form_submits: number;
    call_clicks: number;
    leads_created: number;
    contracted_leads: number;
    collected_revenue_cents: number;
    marketing_spend_cents: number;
    cost_per_lead_cents: number | null;
    cost_per_contract_cents: number | null;
    return_on_ad_spend_basis_points: number | null;
  }>;
  offline_exports: Array<{
    id: string;
    platform: string;
    conversion_event_id: string | null;
    lead_id: string | null;
    revenue_record_id: string | null;
    event_name: string;
    click_id: string;
    click_id_type: string;
    value_cents: number | null;
    currency: string;
    status: string;
    attempt_count: number;
    exported_at: string | null;
    last_error: string | null;
    created_at: string;
  }>;
};

export type ApprovalRequestItem = {
  id: string;
  request_type: string;
  entity_type: string;
  entity_id: string | null;
  status: string;
  title: string;
  summary: string;
  decision_notes: string | null;
  due_at: string | null;
  decided_at: string | null;
  created_at: string;
  review_url: string | null;
};

export type AiControlOverview = {
  summary: {
    agent_count: number;
    active_agent_count: number;
    prompt_version_count: number;
    run_count: number;
    pending_approval_count: number;
    total_cost_cents: number;
    average_latency_ms: number | null;
  };
  agents: Array<{
    id: string;
    key: string;
    name: string;
    description: string;
    status: string;
    model_name: string;
    risk_level: string;
    requires_human_approval: boolean;
    tool_permissions: Array<{
      id: string;
      tool_key: string;
      tool_name: string;
      permission_level: string;
      is_enabled: boolean;
      requires_approval: boolean;
      created_at: string;
    }>;
    created_at: string;
  }>;
  prompt_versions: Array<{
    id: string;
    agent_definition_id: string;
    version_number: number;
    status: string;
    prompt_text: string;
    change_notes: string | null;
    created_at: string;
  }>;
  runs: Array<{
    id: string;
    agent_definition_id: string;
    prompt_version_id: string | null;
    lead_id: string | null;
    status: string;
    model_name: string;
    input_summary: string;
    output_summary: string | null;
    total_tokens: number | null;
    cost_cents: number | null;
    latency_ms: number | null;
    started_at: string;
    completed_at: string | null;
    error_message: string | null;
    tool_calls: Array<{
      id: string;
      ai_run_log_id: string;
      approval_request_id: string | null;
      tool_key: string;
      status: string;
      requires_approval: boolean;
      input_payload: Record<string, unknown> | null;
      output_payload: Record<string, unknown> | null;
      error_message: string | null;
      created_at: string;
    }>;
    created_at: string;
  }>;
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

type BuyerListResponse = {
  items: BuyerListItem[];
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
    console.error("Clerk token unavailable: NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing.");
    return null;
  }
  try {
    const session = await auth();
    const token = await session.getToken();
    if (!token) {
      console.error("Clerk token unavailable: there is no active signed-in session.");
    }
    return token;
  } catch (error) {
    console.error("Clerk token retrieval failed.", error);
    return null;
  }
}

async function apiError(response: Response): Promise<Error> {
  let detail = "No response detail";
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      detail = payload.detail;
    }
  } catch {
    // The API may return an empty or non-JSON error response.
  }
  return new Error(`Stonegate API ${response.status}: ${detail}`);
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
      const failedResponse = [
        summaryResponse,
        leadsResponse,
        speedToLeadResponse,
        openTaskResponse,
      ].find((response) => !response.ok);
      throw await apiError(failedResponse!);
    }

    const summary = (await summaryResponse.json()) as DashboardSummary;
    const leads = ((await leadsResponse.json()) as LeadListResponse).items;
    const speedToLeadQueue = ((await speedToLeadResponse.json()) as SpeedToLeadQueueResponse).items;
    const openTaskQueue = ((await openTaskResponse.json()) as TaskQueueResponse).items;
    return { summary, leads, speedToLeadQueue, openTaskQueue, apiConnected: true };
  } catch (error) {
    console.error("Stonegate dashboard data request failed.", error);
    return {
      summary: emptySummary,
      leads: [],
      speedToLeadQueue: [],
      openTaskQueue: [],
      apiConnected: false,
    };
  }
}

export async function getArchivedLeads(): Promise<{
  leads: LeadListItem[];
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/leads?archived=true`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      leads: ((await response.json()) as LeadListResponse).items,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate archived leads request failed.", error);
    return { leads: [], apiConnected: false };
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

export async function getBuyers(): Promise<{
  buyers: BuyerListItem[];
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/buyers`, {
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("API returned a non-OK response");
    }

    return { buyers: ((await response.json()) as BuyerListResponse).items, apiConnected: true };
  } catch {
    return { buyers: [], apiConnected: false };
  }
}

const emptyFinanceOverview: FinanceOverview = {
  summary: {
    collected_revenue_cents: 0,
    pending_revenue_cents: 0,
    deductions_cents: 0,
    net_revenue_cents: 0,
    compensation_cents: 0,
    marketing_spend_cents: 0,
    company_net_cents: 0,
  },
  revenue_records: [],
  deductions: [],
  compensation_rules: [],
  compensation_calculations: [],
  marketing_spend: [],
};

export async function getFinanceOverview(): Promise<{
  finance: FinanceOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/finance`, {
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("API returned a non-OK response");
    }

    return { finance: (await response.json()) as FinanceOverview, apiConnected: true };
  } catch {
    return { finance: emptyFinanceOverview, apiConnected: false };
  }
}

const emptyMarketingOverview: MarketingOverview = {
  summary: {
    total_spend_cents: 0,
    collected_revenue_cents: 0,
    leads_created: 0,
    contracted_leads: 0,
    cost_per_lead_cents: null,
    cost_per_contract_cents: null,
    return_on_ad_spend_basis_points: null,
    pending_offline_exports: 0,
  },
  campaigns: [],
  offline_exports: [],
};

export async function getMarketingOverview(): Promise<{
  marketing: MarketingOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/marketing`, {
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("API returned a non-OK response");
    }

    return { marketing: (await response.json()) as MarketingOverview, apiConnected: true };
  } catch {
    return { marketing: emptyMarketingOverview, apiConnected: false };
  }
}

const emptyAiControlOverview: AiControlOverview = {
  summary: {
    agent_count: 0,
    active_agent_count: 0,
    prompt_version_count: 0,
    run_count: 0,
    pending_approval_count: 0,
    total_cost_cents: 0,
    average_latency_ms: null,
  },
  agents: [],
  prompt_versions: [],
  runs: [],
};

export async function getAiControlOverview(): Promise<{
  ai: AiControlOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/ai`, {
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("API returned a non-OK response");
    }

    return { ai: (await response.json()) as AiControlOverview, apiConnected: true };
  } catch {
    return { ai: emptyAiControlOverview, apiConnected: false };
  }
}

export async function getApprovalRequests(): Promise<{
  approvals: ApprovalRequestItem[];
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/approvals`, {
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("API returned a non-OK response");
    }

    return {
      approvals: ((await response.json()) as { items: ApprovalRequestItem[] }).items,
      apiConnected: true,
    };
  } catch {
    return { approvals: [], apiConnected: false };
  }
}
