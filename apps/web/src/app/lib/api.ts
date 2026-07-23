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

export type WorkspaceProfile = {
  user_id: string;
  organization_id: string;
  email: string;
  display_name: string;
  role_keys: string[];
  permissions: string[];
  unread_notification_count: number;
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
  property_validation: {
    status: "unverified" | "provider_confirmed" | "needs_review" | "not_found";
    provider: string | null;
    provider_property_id: string | null;
    requested_address: string;
    validated_address: string | null;
    match_score: number | null;
    issues: string[];
    facts: Record<string, unknown>;
    validated_at: string | null;
  };
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

export type OperationsUser = {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  role_keys: string[];
  open_leads: number;
  open_tasks: number;
};

export type AcquisitionOperations = {
  can_manage: boolean;
  users: OperationsUser[];
  teams: Array<{
    id: string;
    name: string;
    team_type: string;
    manager_user_id: string | null;
    manager_name: string | null;
    is_active: boolean;
    members: Array<{
      user_id: string;
      display_name: string;
      email: string;
      membership_role: string;
    }>;
  }>;
  calling_lists: Array<{
    id: string;
    name: string;
    description: string | null;
    status: string;
    default_assignee_user_id: string | null;
    total_records: number;
    completed_records: number;
    interested_records: number;
    entries: Array<{
      id: string;
      lead_id: string;
      seller_name: string;
      property_address: string;
      assigned_user_id: string | null;
      assigned_user_name: string | null;
      status: string;
      attempt_count: number;
      disposition: string | null;
      notes: string | null;
      last_attempt_at: string | null;
      completed_at: string | null;
    }>;
  }>;
  appointments: Array<{
    id: string;
    lead_id: string;
    seller_name: string;
    property_address: string;
    owner_user_id: string | null;
    owner_name: string | null;
    appointment_type: string;
    status: string;
    scheduled_start_at: string;
    scheduled_end_at: string | null;
    outcome: string | null;
    calendar_status: string;
  }>;
  saved_views: Array<{
    id: string;
    name: string;
    resource_type: string;
    filters: Record<string, unknown>;
    is_shared: boolean;
    team_id: string | null;
  }>;
  notifications: Array<{
    id: string;
    notification_type: string;
    title: string;
    body: string;
    entity_type: string | null;
    entity_id: string | null;
    action_url: string | null;
    read_at: string | null;
    created_at: string;
  }>;
  unread_notification_count: number;
  duplicate_candidates: Array<{
    id: string;
    primary_lead_id: string;
    duplicate_lead_id: string;
    primary_label: string;
    duplicate_label: string;
    status: string;
    match_score: number;
    match_reasons: string[];
    resolution_notes: string | null;
    created_at: string;
  }>;
  follow_up_plans: Array<{
    id: string;
    name: string;
    description: string | null;
    status: string;
    steps: Array<{
      delay_days: number;
      action_type: "task" | "call" | "sms" | "email";
      title: string;
      body: string | null;
    }>;
    active_enrollments: number;
  }>;
  markets: Array<{
    id: string;
    name: string;
    code: string;
    state_code: string;
    timezone: string;
    status: string;
    is_primary: boolean;
    territory_count: number;
    campaign_count: number;
    prospect_count: number;
  }>;
  territories: Array<{
    id: string;
    market_id: string;
    market_name: string;
    assigned_team_id: string | null;
    assigned_team_name: string | null;
    name: string;
    code: string;
    status: string;
    county_names: string[];
    postal_codes: string[];
    campaign_count: number;
    prospect_count: number;
  }>;
  campaigns: Array<{
    id: string;
    market_id: string;
    market_name: string;
    territory_id: string | null;
    territory_name: string | null;
    owner_user_id: string | null;
    owner_name: string | null;
    name: string;
    code: string;
    channel: string;
    status: string;
    starts_on: string | null;
    ends_on: string | null;
    budget_cents: number | null;
    prospect_count: number;
    converted_prospect_count: number;
  }>;
  prospects: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    territory_id: string | null;
    territory_name: string | null;
    assigned_user_id: string | null;
    assigned_user_name: string | null;
    converted_lead_id: string | null;
    source_record_key: string | null;
    status: string;
    legal_name: string;
    phone: string | null;
    email: string | null;
    property_address: string | null;
    suppression_status: string;
    phone_validation_status: string;
    address_validation_status: string;
    call_eligibility: string;
    created_at: string;
  }>;
};

export type OperatingModelOverview = {
  users: Array<{
    id: string;
    display_name: string;
    email: string;
    is_active: boolean;
  }>;
  markets: Array<{
    id: string;
    name: string;
    state_code: string;
    status: string;
  }>;
  compensation_plans: Array<{
    id: string;
    name: string;
    version_number: number;
    status: string;
    acquisition_reserve_cents: number;
    target_company_margin_basis_points: number;
    effective_start_at: string | null;
    effective_end_at: string | null;
    created_by_user_id: string;
    created_by_name: string;
    approved_by_user_id: string | null;
    approved_by_name: string | null;
    approved_at: string | null;
    notes: string | null;
    roles: Array<{
      id: string;
      role_key: string;
      basis_points: number;
      cap_cents: number | null;
      notes: string | null;
    }>;
    disposition_modes: Array<{
      id: string;
      key: string;
      name: string;
      status: string;
      human_share_min_basis_points: number;
      human_share_max_basis_points: number;
      expected_company_share_min_basis_points: number;
      expected_company_share_max_basis_points: number;
      ai_authority_level: string;
      activation_requirements: Record<string, unknown>;
    }>;
  }>;
  role_credits: Array<{
    id: string;
    compensation_plan_version_id: string;
    plan_label: string;
    lead_id: string;
    seller_name: string;
    user_id: string;
    user_name: string;
    role_key: string;
    credit_basis_points: number;
    status: string;
    assigned_by_user_id: string;
    assigned_by_name: string;
    approved_by_user_id: string | null;
    approved_by_name: string | null;
    approved_at: string | null;
    notes: string | null;
    created_at: string;
  }>;
  launch_checklists: Array<{
    id: string;
    market_id: string;
    market_name: string;
    version_number: number;
    status: string;
    owner_user_id: string;
    owner_name: string;
    approved_by_user_id: string | null;
    approved_by_name: string | null;
    approved_at: string | null;
    notes: string | null;
    completed_items: number;
    total_items: number;
    items: Array<{
      id: string;
      item_key: string;
      category: string;
      label: string;
      status: string;
      responsible_user_id: string | null;
      responsible_user_name: string | null;
      evidence_notes: string | null;
      completed_by_user_id: string | null;
      completed_by_name: string | null;
      completed_at: string | null;
      sort_order: number;
    }>;
  }>;
};

export type CampaignManagementOverview = {
  users: OperationsUser[];
  campaigns: AcquisitionOperations["campaigns"];
  mappings: Array<{
    id: string;
    name: string;
    source_name: string | null;
    field_mapping: Record<string, string>;
    default_values: Record<string, string>;
    created_by_user_id: string;
    created_by_name: string;
    is_active: boolean;
    created_at: string;
  }>;
  import_batches: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    mapping_id: string;
    mapping_name: string;
    default_assignee_user_id: string | null;
    default_assignee_name: string | null;
    imported_by_user_id: string;
    imported_by_name: string;
    file_name: string;
    file_sha256: string;
    status: string;
    total_rows: number;
    valid_rows: number;
    imported_rows: number;
    invalid_rows: number;
    duplicate_rows: number;
    suppressed_rows: number;
    review_required_rows: number;
    completed_at: string | null;
    created_at: string;
    rows: Array<{
      id: string;
      row_number: number;
      status: string;
      prospect_id: string | null;
      duplicate_prospect_id: string | null;
      legal_name: string | null;
      phone: string | null;
      property_address: string | null;
      validation_errors: string[];
      eligibility_reasons: string[];
    }>;
  }>;
  costs: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    import_batch_id: string | null;
    worker_user_id: string | null;
    worker_name: string | null;
    category: string;
    vendor_name: string | null;
    amount_cents: number;
    labor_minutes: number | null;
    hourly_rate_cents: number | null;
    incurred_on: string;
    notes: string | null;
    created_at: string;
  }>;
  calling_batches: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    import_batch_id: string | null;
    assigned_user_id: string;
    assigned_user_name: string;
    name: string;
    status: string;
    due_at: string | null;
    notes: string | null;
    total_entries: number;
    completed_entries: number;
    created_at: string;
    entries: Array<{
      id: string;
      prospect_id: string;
      legal_name: string;
      phone: string | null;
      property_address: string | null;
      sequence_number: number;
      status: string;
      attempt_count: number;
      disposition: string | null;
      call_eligibility: string;
    }>;
  }>;
  screening_review: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    legal_name: string;
    phone: string | null;
    property_address: string | null;
    call_eligibility: string;
    suppression_status: string;
    suppression_checked_at: string | null;
  }>;
  quality: Array<{
    campaign_id: string;
    campaign_name: string;
    budget_cents: number | null;
    actual_cost_cents: number;
    remaining_budget_cents: number | null;
    total_import_rows: number;
    imported_prospects: number;
    callable_prospects: number;
    review_required_prospects: number;
    blocked_prospects: number;
    converted_prospects: number;
    invalid_rows: number;
    duplicate_rows: number;
    suppressed_rows: number;
    bad_data_rate_basis_points: number;
    duplicate_rate_basis_points: number;
    conversion_rate_basis_points: number;
    cost_per_imported_prospect_cents: number | null;
    cost_per_callable_prospect_cents: number | null;
    calling_batch_entries: number;
    calling_batch_completed: number;
  }>;
};

export type ProspectingScript = {
  id: string;
  version_number: number;
  title: string;
  status: string;
  opening_script: string;
  qualification_questions: Array<{
    key: string;
    label: string;
    prompt: string;
    answer_type: "text" | "choice";
    choices: string[];
    required_for_handoff: boolean;
  }>;
  created_by_name: string;
  approved_by_name: string | null;
  approved_at: string | null;
  created_at: string;
};

export type ProspectingAttempt = {
  id: string;
  script_version_id: string;
  script_version_number: number;
  status: string;
  outcome: string | null;
  contact_made: boolean | null;
  qualification_answers: Record<string, string>;
  notes: string | null;
  callback_at: string | null;
  started_at: string;
  completed_at: string | null;
  quality_score_basis_points: number | null;
};

export type ProspectingEntry = {
  id: string;
  batch_id: string;
  batch_name: string;
  campaign_name: string;
  prospect_id: string;
  legal_name: string;
  phone: string | null;
  email: string | null;
  property_address: string | null;
  sequence_number: number;
  status: string;
  attempt_count: number;
  disposition: string | null;
  next_attempt_at: string | null;
  active_attempt: ProspectingAttempt | null;
  attempts: ProspectingAttempt[];
};

export type ProspectHandoff = {
  id: string;
  prospect_id: string;
  attempt_id: string;
  lead_id: string;
  seller_name: string;
  property_address: string | null;
  caller_name: string;
  assigned_user_id: string;
  assigned_user_name: string;
  status: string;
  outcome: string;
  qualification_answers: Record<string, string>;
  notes: string | null;
  submitted_at: string;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_reason: string | null;
};

export type ProspectingCopilotOutput = {
  pre_call_summary: string;
  priority_explanation: string;
  property_context: string[];
  prior_attempt_context: string[];
  opening_guidance: string;
  required_questions: string[];
  disposition_guidance: string[];
  data_quality_warnings: string[];
  compliance_reminders: string[];
  evidence: string[];
  confidence: number;
};

export type ProspectingCopilotRecommendation = {
  id: string;
  entry_id: string;
  prospect_id: string;
  ai_run_log_id: string | null;
  status: string;
  priority_score: number;
  priority_band: string;
  output_payload: ProspectingCopilotOutput;
  confidence_score: number | null;
  generated_at: string;
  reviewed_at: string | null;
};

export type ProspectingCallQualityOutput = {
  call_summary: string;
  suggested_disposition: string;
  disposition_reason: string;
  callback_recommendation: string;
  handoff_draft: string;
  script_adherence_score: number;
  qualification_completeness_score: number;
  objection_handling_score: number;
  data_quality_score: number;
  handoff_quality_score: number;
  coaching_points: string[];
  compliance_flags: string[];
  evidence_timestamps: string[];
  confidence: number;
};

export type ProspectingCallQuality = {
  id: string;
  attempt_id: string;
  caller_user_id: string;
  caller_name: string;
  seller_name: string;
  outcome: string | null;
  status: string;
  deterministic_scores: Record<string, number | null>;
  ai_output: ProspectingCallQualityOutput | null;
  final_output: ProspectingCallQualityOutput | null;
  compliance_flags: string[];
  escalation_required: boolean;
  transcript_available: boolean;
  reviewed_at: string | null;
  review_notes: string | null;
  completed_at: string | null;
};

export type ProspectingWorkbenchOverview = {
  current_user_id: string;
  current_user_name: string;
  can_manage: boolean;
  active_script: ProspectingScript | null;
  scripts: ProspectingScript[];
  current_entry: ProspectingEntry | null;
  queue: {
    ready: number;
    callbacks_due: number;
    in_progress: number;
    handoff_pending: number;
    completed: number;
  };
  acquisition_users: OperationsUser[];
  pending_handoffs: ProspectHandoff[];
  returned_handoffs: ProspectHandoff[];
  scorecards: Array<{
    caller_user_id: string;
    caller_name: string;
    score_date: string;
    attempts: number;
    contacts: number;
    callbacks: number;
    handoffs: number;
    accepted_handoffs: number;
    wrong_numbers: number;
    dnc_requests: number;
    contact_rate_basis_points: number;
    handoff_rate_basis_points: number;
    accepted_handoff_rate_basis_points: number;
    script_completion_rate_basis_points: number;
    data_quality_issue_rate_basis_points: number;
  }>;
  copilot: {
    pilot_mode: string;
    runtime_status: string;
    priority_capability_status: string;
    quality_capability_status: string;
    external_actions_blocked: boolean;
    work_items: Array<{
      entry_id: string;
      prospect_id: string;
      seller_name: string;
      property_address: string | null;
      campaign_name: string;
      priority_score: number;
      priority_band: string;
      recommended_action: string;
      reasons: string[];
      data_quality_warnings: string[];
      eligibility_evidence: string[];
      callback_due: boolean;
      correction_required: boolean;
    }>;
    recommendations: ProspectingCopilotRecommendation[];
    quality_queue: ProspectingCallQuality[];
    metrics: {
      generated_briefs: number;
      reviewed_briefs: number;
      accepted_or_corrected_rate_basis_points: number;
      correction_rate_basis_points: number;
      estimated_time_saved_minutes: number;
      quality_reviews: number;
      transcript_ready: number;
      escalations: number;
      coaching_approved: number;
      coaching_corrected: number;
    };
  };
};

export type LeadManagerQualificationScript = {
  id: string;
  version_number: number;
  title: string;
  status: string;
  introduction: string;
  questions: Array<{
    key: string;
    label: string;
    prompt: string;
    answer_type: "text" | "choice" | "boolean";
    choices: string[];
    required: boolean;
  }>;
  approved_at: string | null;
  created_at: string;
};

export type LeadManagerCase = {
  id: string;
  lead_id: string;
  handoff_id: string | null;
  seller_name: string;
  property_address: string;
  source: string;
  stage_key: string;
  assigned_user_id: string;
  assigned_user_name: string;
  status: string;
  acceptance_due_at: string;
  accepted_at: string | null;
  escalated_at: string | null;
  acceptance_minutes: number | null;
  is_acceptance_overdue: boolean;
  qualification_completed_at: string | null;
  qualification_quality_basis_points: number | null;
  next_action_type: string | null;
  next_action_due_at: string | null;
  is_next_action_overdue: boolean;
  age_hours: number;
  lead_url: string;
};

export type LeadManagerCopilotOutput = {
  summary: string;
  priority_explanation: string;
  qualification_gaps: string[];
  recommended_questions: string[];
  message_draft: {
    channel: "none" | "sms" | "email";
    body: string;
  };
  next_task: {
    title: string;
    reason: string;
    due_timing: string;
  };
  appointment_proposal: {
    recommended: boolean;
    reason: string;
  };
  handoff_summary: string;
  risks: string[];
  evidence: string[];
  confidence: number;
};

export type LeadManagerCopilotRecommendation = {
  id: string;
  case_id: string;
  lead_id: string;
  ai_run_log_id: string | null;
  status: string;
  priority_score: number;
  priority_band: string;
  model_name: string | null;
  output_payload: LeadManagerCopilotOutput;
  evidence_snapshot: Record<string, unknown>;
  confidence_score: number | null;
  generated_at: string;
  reviewed_at: string | null;
};

export type LeadManagerOverview = {
  current_user_id: string;
  current_user_name: string;
  can_manage: boolean;
  metrics: {
    awaiting_acceptance: number;
    overdue_acceptance: number;
    qualification_due: number;
    follow_up_due: number;
    appointments_today: number;
    neglected_leads: number;
  };
  active_script: LeadManagerQualificationScript | null;
  scripts: LeadManagerQualificationScript[];
  awaiting_acceptance: LeadManagerCase[];
  qualification_queue: LeadManagerCase[];
  follow_up_queue: LeadManagerCase[];
  appointments_today: LeadManagerCase[];
  neglected_queue: LeadManagerCase[];
  scorecards: Array<{
    user_id: string;
    user_name: string;
    handoffs_received: number;
    handoffs_accepted: number;
    accepted_within_sla: number;
    average_acceptance_minutes: number | null;
    qualifications_completed: number;
    appointments_set: number;
    appointments_held: number;
    appointment_no_shows: number;
    contracts_created: number;
    follow_up_quality_basis_points: number;
  }>;
  copilot: {
    pilot_mode: string;
    runtime_status: string;
    capability_status: string;
    external_actions_blocked: boolean;
    work_items: Array<{
      case_id: string;
      lead_id: string;
      seller_name: string;
      property_address: string;
      assigned_user_name: string;
      priority_score: number;
      priority_band: string;
      recommended_action: string;
      alerts: string[];
      qualification_gaps: string[];
      recommended_questions: string[];
      evidence: string[];
      missed_reply: boolean;
      appointment_today: boolean;
      lead_url: string;
    }>;
    recommendations: LeadManagerCopilotRecommendation[];
    metrics: {
      generated_count: number;
      reviewed_count: number;
      accepted_count: number;
      edited_count: number;
      rejected_count: number;
      acceptance_rate_basis_points: number;
      correction_rate_basis_points: number;
      estimated_time_saved_minutes: number;
      total_cost_microusd: number;
      average_response_minutes: number | null;
      appointments_set: number;
    };
  };
};

export type DispatchCandidate = {
  profile_id: string;
  user_id: string;
  user_name: string;
  eligible: boolean;
  territory_match: boolean;
  territory_name: string | null;
  daily_booked_count: number;
  daily_capacity: number;
  remaining_capacity: number;
  travel_buffer_minutes: number;
  violations: string[];
};

export type DispatchSlotEvaluation = {
  lead_id: string;
  scheduled_start_at: string;
  scheduled_end_at: string;
  territory_id: string | null;
  territory_name: string | null;
  candidates: DispatchCandidate[];
};

export type FieldOperationsOverview = {
  can_manage: boolean;
  metrics: {
    ready_to_schedule: number;
    appointments_today: number;
    unassigned_today: number;
    at_capacity_today: number;
  };
  users: Array<{
    id: string;
    name: string;
    email: string;
    profile_configured: boolean;
  }>;
  profiles: Array<{
    id: string;
    user_id: string;
    user_name: string;
    timezone: string;
    working_days: number[];
    workday_start_minute: number;
    workday_end_minute: number;
    daily_capacity: number;
    default_appointment_minutes: number;
    travel_buffer_minutes: number;
    home_base_postal_code: string | null;
    territory_enforcement_enabled: boolean;
    is_active: boolean;
    territory_ids: string[];
    territory_names: string[];
    blocks: Array<{
      id: string;
      block_type: string;
      starts_at: string;
      ends_at: string;
      reason: string;
    }>;
  }>;
  territories: Array<{
    id: string;
    name: string;
    market_name: string;
    county_names: string[];
    postal_codes: string[];
  }>;
  ready_leads: Array<{
    id: string;
    seller_name: string;
    property_address: string;
    county: string | null;
    postal_code: string;
    stage_key: string;
    current_owner_name: string | null;
    next_follow_up_at: string | null;
    lead_url: string;
  }>;
  upcoming_appointments: Array<{
    id: string;
    lead_id: string;
    seller_name: string;
    property_address: string;
    closer_name: string;
    status: string;
    scheduled_start_at: string;
    scheduled_end_at: string | null;
    decision_status: string | null;
    violations: string[];
    lead_url: string;
  }>;
  scorecards: Array<{
    user_id: string;
    user_name: string;
    assigned_appointments: number;
    briefs_prepared: number;
    inspections_submitted: number;
    outcomes_recorded: number;
    accepted_outcomes: number;
    follow_up_outcomes: number;
    declined_outcomes: number;
    preparation_rate_basis_points: number;
    documentation_rate_basis_points: number;
  }>;
};

export type FieldCalendarAppointment = {
  id: string;
  lead_id: string;
  seller_name: string;
  property_address: string;
  closer_user_id: string | null;
  closer_name: string;
  appointment_type: string;
  status: string;
  scheduled_start_at: string;
  scheduled_end_at: string | null;
  location_type: string;
  outcome: string | null;
  field_status: string;
  lead_url: string;
};

export type FieldMeetingBrief = {
  id: string;
  appointment_id: string;
  version_number: number;
  status: string;
  source_snapshot: Record<string, unknown>;
  brief_data: Record<string, unknown>;
  created_at: string;
};

export type FieldRoomObservation = {
  area: string;
  condition: "good" | "fair" | "poor" | "not_inspected";
  notes: string | null;
};

export type FieldRepairItem = {
  category: string;
  estimated_cost_cents: number;
  details: string | null;
};

export type FieldInspection = {
  id: string;
  appointment_id: string;
  lead_id: string;
  property_id: string;
  inspector_user_id: string;
  inspector_name: string;
  status: string;
  started_at: string;
  submitted_at: string | null;
  reviewed_at: string | null;
  overall_condition: string | null;
  occupancy_observed: string | null;
  utilities_status: string | null;
  access_notes: string | null;
  title_concerns: string | null;
  safety_concerns: string | null;
  room_observations: FieldRoomObservation[];
  repair_items: FieldRepairItem[];
  inspector_notes: string | null;
  photos: Array<{
    id: string;
    area: string;
    caption: string | null;
    file_name: string;
    content_type: string;
    byte_size: number;
    sha256: string;
    captured_at: string | null;
    content_url: string;
    created_at: string;
  }>;
  repair_total_cents: number;
};

export type FieldNegotiation = {
  id: string;
  appointment_id: string;
  lead_id: string;
  recorded_by_user_id: string;
  governing_concession_id: string | null;
  decision_makers_confirmed: boolean;
  decision_makers: string[];
  seller_asking_price_cents: number | null;
  offer_presented_cents: number | null;
  seller_counter_cents: number | null;
  agreed_price_cents: number | null;
  approved_ceiling_cents: number | null;
  objections: Array<{
    category: string;
    details: string;
    response: string | null;
    resolved: boolean;
  }>;
  commitments: string[];
  outcome: string;
  notes: string | null;
  next_follow_up_at: string | null;
  updated_at: string;
};

export type AcquisitionsCopilotRecommendation = {
  id: string;
  appointment_id: string;
  lead_id: string;
  recommendation_type: "preparation" | "follow_up";
  ai_run_log_id: string | null;
  status: "draft" | "accepted" | "edited" | "rejected";
  output_payload: Record<string, unknown>;
  confidence_score: number | null;
  generated_at: string;
  reviewed_at: string | null;
};

export type AcquisitionsCopilotOverview = {
  pilot_mode: string;
  runtime_status: string;
  preparation_capability_status: string;
  follow_up_capability_status: string;
  external_actions_blocked: boolean;
  readiness_score: number;
  readiness_band: string;
  readiness_gaps: string[];
  evidence_available: string[];
  authority_status: string;
  approved_ceiling_cents: number | null;
  recommendations: AcquisitionsCopilotRecommendation[];
  metrics: {
    generated: number;
    reviewed: number;
    accepted_or_corrected_rate_basis_points: number;
    correction_rate_basis_points: number;
    estimated_time_saved_minutes: number;
  };
};

export type FieldAppointmentWorkspace = {
  appointment: FieldCalendarAppointment;
  brief: FieldMeetingBrief | null;
  inspection: FieldInspection | null;
  negotiation: FieldNegotiation | null;
  underwriting_transfer: {
    id: string;
    inspection_id: string;
    source_underwriting_version_id: string | null;
    repair_estimate_id: string | null;
    created_underwriting_version_id: string;
    created_underwriting_version_number: number;
    created_at: string;
  } | null;
  copilot: AcquisitionsCopilotOverview;
  can_edit: boolean;
  can_review_underwriting: boolean;
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
    arv_point_cents: number | null;
    total_rehab_cents: number | null;
    recommended_disposition_cents: number | null;
    seller_contract_ceiling_cents: number | null;
    report_stage: string | null;
    repair_estimate_source: string | null;
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
  reliability_score_basis_points: number;
  completed_deals: number;
  failed_deals: number;
  proof_of_funds_expires_at: string | null;
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

export type DispositionMatch = {
  id: string;
  buyer_id: string;
  buyer_name: string;
  score_basis_points: number;
  score_components: Record<string, number>;
  qualification_status: string;
  recipient_status: string;
  rank: number;
  proof_status: string;
  proof_expires_at: string | null;
  latest_proof_document_id: string | null;
};

export type DispositionOffer = {
  id: string;
  buyer_id: string;
  buyer_name: string;
  amount_cents: number;
  earnest_money_cents: number | null;
  financing_type: string;
  status: string;
  proof_document_id: string | null;
  deposit_due_at: string | null;
  deposit_received_at: string | null;
  selected_at: string | null;
  notes: string | null;
  received_at: string;
};

export type DispositionCase = {
  id: string;
  transaction_id: string;
  lead_id: string;
  seller_name: string;
  property_address: string;
  property_type: string | null;
  status: string;
  strategy: string;
  asking_price_cents: number;
  minimum_acceptable_cents: number;
  package_status: string;
  package_snapshot: Record<string, unknown>;
  compensation_plan_label: string;
  operating_mode_label: string;
  selected_buyer_id: string | null;
  backup_buyer_id: string | null;
  matches: DispositionMatch[];
  offers: DispositionOffer[];
  engagements: Array<{
    id: string; buyer_id: string; buyer_name: string; engagement_type: string;
    status: string; scheduled_at: string | null; occurred_at: string; notes: string | null;
  }>;
  reconciliation: null | {
    id: string; status: string; gross_revenue_cents: number; acquisition_reserve_cents: number;
    deal_deductions_cents: number; adjusted_deal_margin_cents: number;
    total_compensation_cents: number; company_profit_cents: number;
    company_margin_basis_points: number; target_margin_basis_points: number; notes: string | null;
    payouts: Array<{ id: string; role_key: string; user_id: string | null; user_name: string | null; credit_basis_points: number; amount_cents: number; status: string }>;
    created_at: string;
  };
  created_at: string;
};

export type DispositionOverview = {
  metrics: { active_cases: number; packages_pending: number; buyer_selected: number; reconciliation_pending: number; below_margin_target: number };
  eligible_transactions: Array<{ id: string; seller_name: string; property_address: string; purchase_price_cents: number; assignment_fee_cents: number | null }>;
  cases: DispositionCase[];
};

export type DispositionCopilotRecommendation = {
  id: string;
  disposition_case_id: string;
  transaction_id: string;
  lead_id: string;
  ai_run_log_id: string | null;
  status: string;
  output_payload: {
    status_summary: string;
    package_gaps: string[];
    package_highlights: string[];
    recommended_buyers: Array<{
      buyer_id: string;
      buyer_name: string;
      recommendation: "priority" | "backup" | "hold" | "exclude";
      rationale: string[];
      risks: string[];
      evidence: string[];
    }>;
    offer_comparison: Array<{
      offer_id: string;
      buyer_name: string;
      strength: "strong" | "acceptable" | "weak" | "ineligible";
      rationale: string[];
      risks: string[];
    }>;
    buyer_outreach_subject: string;
    buyer_outreach_body: string;
    recommended_internal_actions: string[];
    relationship_update_proposals: string[];
    risk_alerts: string[];
    uncertainties: string[];
    evidence: string[];
    confidence: number;
  };
  confidence_score: number | null;
  generated_at: string;
  reviewed_at: string | null;
};

export type DispositionCopilotOverview = {
  pilot_mode: "draft_only";
  runtime_status: string;
  capability_status: string;
  external_actions_blocked: boolean;
  readiness_score: number;
  readiness_band: "ready" | "needs_review" | "blocked";
  readiness_gaps: string[];
  risk_alerts: Array<{
    severity: "info" | "warning" | "critical";
    item: string;
    reason: string;
    evidence: string[];
  }>;
  qualified_buyer_count: number;
  verified_buyer_count: number;
  offer_count: number;
  backup_coverage: boolean;
  recommendations: DispositionCopilotRecommendation[];
  metrics: {
    generated: number;
    reviewed: number;
    accepted_or_corrected_rate_basis_points: number;
    correction_rate_basis_points: number;
    estimated_time_saved_minutes: number;
  };
};

export type FinanceSummary = {
  collected_revenue_cents: number;
  pending_revenue_cents: number;
  deductions_cents: number;
  net_revenue_cents: number;
  compensation_cents: number;
  marketing_spend_cents: number;
  company_net_cents: number;
};

export type FinanceOverview = {
  period_days: number | null;
  period_start_at: string | null;
  period_end_at: string;
  previous_summary: FinanceSummary | null;
  summary: FinanceSummary;
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

export type MarketingSummary = {
  total_spend_cents: number;
  collected_revenue_cents: number;
  leads_created: number;
  contracted_leads: number;
  cost_per_lead_cents: number | null;
  cost_per_contract_cents: number | null;
  return_on_ad_spend_basis_points: number | null;
  pending_offline_exports: number;
};

export type MarketingOverview = {
  period_days: number | null;
  period_start_at: string | null;
  period_end_at: string;
  previous_summary: MarketingSummary | null;
  summary: MarketingSummary;
  public_funnel: {
    page_views: number;
    offer_starts: number;
    form_starts: number;
    step_completions: Record<string, number>;
    validation_errors: number;
    submit_attempts: number;
    form_submits: number;
    submit_errors: number;
    form_abandons: number;
    start_to_submit_rate_basis_points: number | null;
  };
  web_vitals: Array<{
    metric: string;
    sample_count: number;
    p75_value: number;
    good_rate_basis_points: number;
  }>;
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
  decided_by_user_id: string | null;
  due_at: string | null;
  decided_at: string | null;
  created_at: string;
  review_url: string | null;
  approval_metadata: Record<string, unknown>;
};

export type AiCapabilityContract = {
  id: string;
  copilot_definition_id: string;
  capability_key: string;
  name: string;
  version_number: number;
  status: string;
  owner_role_key: string;
  trigger_events: string[];
  input_requirements: string[];
  output_requirements: string[];
  allowed_tool_scopes: string[];
  evidence_requirements: string[];
  approval_policy: {
    initial_level?: string;
    human_approval_required_for?: string[];
    external_execution_enabled?: boolean;
  };
  escalation_policy: {
    when?: string[];
    preserve_complete_history?: boolean;
    stop_on_uncertainty?: boolean;
  };
  prohibited_actions: string[];
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
};

export type AiCopilotFoundation = {
  status: string;
  copilots: Array<{
    id: string;
    key: string;
    name: string;
    description: string;
    human_owner_role_key: string;
    human_owner_title: string;
    human_authority_summary: string;
    status: string;
    phase_key: string;
    approved_by_user_id: string | null;
    approved_at: string | null;
    specialist_mappings: Array<{
      id: string;
      agent_definition_id: string;
      agent_key: string;
      agent_name: string;
      purpose: string;
      display_order: number;
    }>;
    capability_contracts: AiCapabilityContract[];
    created_at: string;
  }>;
  data_governance_policies: Array<{
    id: string;
    key: string;
    name: string;
    data_category: string;
    field_scope: string[];
    version_number: number;
    status: string;
    source_precedence: string[];
    overwrite_policy: string;
    redaction_rule: string;
    retention_rule: string;
    permitted_role_keys: string[];
    approved_by_user_id: string | null;
    approved_at: string | null;
    created_at: string;
  }>;
  knowledge_sources: Array<{
    id: string;
    key: string;
    title: string;
    category: string;
    source_type: string;
    content_reference: string;
    version_number: number;
    status: string;
    owner_role_key: string;
    audience_role_keys: string[];
    is_authoritative: boolean;
    effective_at: string | null;
    review_due_at: string | null;
    content_checksum: string | null;
    content_snapshot: string | null;
    approved_by_user_id: string | null;
    approved_at: string | null;
    created_at: string;
  }>;
  data_quality_rules: Array<{
    id: string;
    key: string;
    name: string;
    record_type: string;
    field_scope: string[];
    rule_type: string;
    severity: string;
    is_deterministic: boolean;
    configuration: Record<string, unknown>;
    resolution_action: string;
    version_number: number;
    status: string;
    approved_by_user_id: string | null;
    approved_at: string | null;
    created_at: string;
  }>;
};

export type AiControlOverview = {
  summary: {
    agent_count: number;
    active_agent_count: number;
    prompt_version_count: number;
    run_count: number;
    pending_approval_count: number;
    total_cost_cents: number;
    total_cost_microusd: number;
    unpriced_run_count: number;
    average_latency_ms: number | null;
  };
  call_intelligence_quality: {
    total_calls: number;
    reviewed_calls: number;
    approved_calls: number;
    rejected_calls: number;
    pending_review_calls: number;
    failed_calls: number;
    average_confidence: number | null;
    average_field_agreement: number | null;
    average_evidence_coverage: number | null;
    high_correction_calls: number;
    minimum_review_sample: number;
    autonomy_status: string;
    autonomy_blockers: string[];
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
    autonomy_level: string;
    max_cost_microusd_per_run: number;
    max_daily_cost_microusd: number;
    max_attempts: number;
    rollback_owner_user_id: string | null;
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
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    cost_cents: number | null;
    cost_microusd: number | null;
    latency_ms: number | null;
    started_at: string;
    completed_at: string | null;
    error_message: string | null;
    run_metadata: Record<string, unknown> | null;
    orchestrator_event_id: string | null;
    parent_run_id: string | null;
    execution_mode: string;
    capability_key: string;
    attempt_number: number;
    idempotency_key: string | null;
    budget_limit_microusd: number | null;
    budget_status: string;
    trace_status: string;
    trace_reviewed_by_user_id: string | null;
    trace_reviewed_at: string | null;
    trace_review_notes: string | null;
    rollback_status: string;
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
  orchestrator: {
    metrics: {
      portfolio_agent_count: number;
      copilot_count: number;
      active_copilot_count: number;
      governed_run_count: number;
      unreviewed_trace_count: number;
      approved_dataset_count: number;
      passing_evaluation_count: number;
      pending_promotion_count: number;
      active_promotion_count: number;
      budget_blocked_run_count: number;
    };
    foundation: AiCopilotFoundation;
    events: Array<{
      id: string;
      event_key: string;
      event_type: string;
      status: string;
      occurred_at: string;
    }>;
    datasets: Array<{
      id: string;
      agent_definition_id: string;
      capability_key: string;
      dataset_key: string;
      name: string;
      version_number: number;
      status: string;
      description: string | null;
      minimum_case_count: number;
      minimum_pass_rate_basis_points: number;
      minimum_factual_accuracy_basis_points: number;
      minimum_evidence_coverage_basis_points: number;
      maximum_critical_failures: number;
      maximum_average_latency_ms: number | null;
      maximum_average_cost_microusd: number | null;
      owner_role_key: string;
      case_schema_version: number;
      reviewer_instructions: string;
      disagreement_policy: string;
      redaction_policy: Record<string, unknown>;
      required_review_scopes: string[];
      reviews: Array<{
        id: string;
        review_scope: string;
        reviewer_role_key: string;
        status: string;
        notes: string;
        reviewed_by_user_id: string;
        reviewed_at: string;
      }>;
      approved_by_user_id: string | null;
      approved_at: string | null;
      cases: Array<{
        id: string;
        case_key: string;
        name: string;
        input_payload: Record<string, unknown>;
        expected_output: Record<string, unknown>;
        candidate_output: Record<string, unknown> | null;
        deterministic_checks: Record<string, unknown>;
        risk_tags: string[];
        is_critical: boolean;
        case_type: string;
        scenario_family: string;
        source_type: string;
        source_reference: string | null;
        redaction_status: string;
        expected_uncertainty: string[];
        required_evidence: string[];
        prohibited_behaviors: string[];
        reviewer_notes: string;
      }>;
      created_at: string;
    }>;
    evaluation_runs: Array<{
      id: string;
      dataset_id: string;
      prompt_version_id: string;
      status: string;
      case_count: number;
      passed_case_count: number;
      pass_rate_basis_points: number;
      factual_accuracy_basis_points: number;
      evidence_coverage_basis_points: number;
      critical_failure_count: number;
      thresholds_passed: boolean;
      created_at: string;
    }>;
    promotions: Array<{
      id: string;
      agent_definition_id: string;
      capability_key: string;
      evaluation_run_id: string;
      approval_request_id: string | null;
      from_level: string;
      to_level: string;
      status: string;
      reason: string;
      effective_at: string | null;
      rolled_back_at: string | null;
      rollback_reason: string | null;
      created_at: string;
    }>;
    runtime: {
      status: string;
      policy: {
        id: string;
        provider_status: string;
        emergency_stop: boolean;
        emergency_stop_reason: string | null;
        high_volume_model: string;
        default_model: string;
        escalation_model: string;
        max_context_characters: number;
        max_requests_per_minute: number;
        max_daily_cost_microusd: number;
        circuit_failure_threshold: number;
        circuit_cooldown_seconds: number;
        consecutive_failure_count: number;
        circuit_open_until: string | null;
        trace_redaction_enabled: boolean;
        external_actions_enabled: boolean;
        updated_at: string;
      } | null;
      capabilities: Array<{
        id: string;
        agent_definition_id: string;
        agent_name: string;
        capability_key: string;
        status: string;
        model_route: string;
        output_schema: Record<string, unknown>;
        allowed_tool_keys: string[];
        allowed_knowledge_keys: string[];
        max_output_tokens: number;
        max_cost_microusd_per_run: number;
        requires_human_review: boolean;
        updated_at: string;
      }>;
      comparisons: Array<{
        id: string;
        dataset_id: string;
        baseline_evaluation_run_id: string;
        challenger_evaluation_run_id: string;
        status: string;
        regression_blocked: boolean;
        quality_delta_basis_points: number;
        latency_delta_ms: number | null;
        cost_delta_microusd: number | null;
        summary: Record<string, unknown>;
        created_at: string;
      }>;
      metrics: {
        enabled_capability_count: number;
        blocked_run_count: number;
        failed_run_count: number;
        redacted_trace_count: number;
        knowledge_use_count: number;
        regression_block_count: number;
      };
    };
  };
};

export type UnderwritingCalibrationCase = {
  id: string;
  lead_id: string;
  analysis_id: string;
  seller_name: string;
  property_address: string;
  market_key: string;
  benchmark_type: string;
  evidence_date: string;
  benchmark_arv_cents: number;
  actual_rehab_cents: number | null;
  actual_seller_contract_cents: number | null;
  actual_disposition_cents: number | null;
  predicted_arv_low_cents: number | null;
  predicted_arv_point_cents: number | null;
  predicted_arv_high_cents: number | null;
  predicted_rehab_cents: number | null;
  predicted_seller_ceiling_cents: number | null;
  predicted_disposition_cents: number | null;
  arv_error_cents: number | null;
  arv_error_percentage: number | null;
  arv_absolute_error_percentage: number | null;
  arv_range_hit: boolean | null;
  evidence_reference: string | null;
  notes: string | null;
  recorded_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type UnderwritingCalibrationMetric = {
  market_key: string;
  sample_count: number;
  median_error_percentage: number | null;
  median_absolute_error_percentage: number | null;
  range_coverage_percentage: number | null;
  overestimate_count: number;
  underestimate_count: number;
  balanced_count: number;
  repair_sample_count: number;
  repair_median_absolute_error_percentage: number | null;
  disposition_sample_count: number;
  disposition_median_absolute_error_percentage: number | null;
  readiness: string;
};

export type UnderwritingCalibration = {
  overall: UnderwritingCalibrationMetric;
  markets: UnderwritingCalibrationMetric[];
  cases: UnderwritingCalibrationCase[];
  uncalibrated_analysis_count: number;
  minimum_sample_for_formula_review: number;
  automatic_formula_changes_enabled: boolean;
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

export type TransactionQueueItem = {
  id: string;
  lead_id: string;
  seller_name: string;
  property_address: string;
  status: string;
  purchase_price_cents: number;
  closing_date: string | null;
  next_deadline: string | null;
  coordinator_name: string | null;
  checklist_complete: number;
  checklist_total: number;
  risk_flags: string[];
};

export type TransactionOverview = {
  metrics: {
    active: number;
    pending_approval: number;
    due_next_seven_days: number;
    overdue: number;
    ready_to_close: number;
  };
  items: TransactionQueueItem[];
};

export type TransactionDetail = {
  id: string;
  lead_id: string;
  deal_id: string;
  seller_name: string;
  property_address: string;
  status: string;
  contract_type: string;
  purchase_price_cents: number;
  assignment_fee_cents: number | null;
  earnest_money_cents: number | null;
  title_company: string | null;
  closing_date: string | null;
  inspection_period_days: number | null;
  coordinator_user_id: string | null;
  coordinator_name: string | null;
  earnest_money_due_at: string | null;
  earnest_money_paid_at: string | null;
  due_diligence_deadline: string | null;
  title_opened_at: string | null;
  title_cleared_at: string | null;
  assignment_deadline: string | null;
  funded_at: string | null;
  closed_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  contract_packages: Array<{
    id: string;
    version_number: number;
    template_id: string | null;
    status: string;
    seller_name: string;
    buyer_entity_name: string;
    purchase_price_cents: number;
    earnest_money_cents: number | null;
    closing_date: string | null;
    inspection_period_days: number | null;
    approval_request_id: string | null;
    notes: string | null;
    approved_at: string | null;
    sent_at: string | null;
    executed_at: string | null;
    created_at: string;
  }>;
  documents: Array<{
    id: string;
    contract_package_id: string | null;
    document_type: string;
    title: string;
    status: string;
    file_name: string;
    content_type: string;
    file_size: number;
    occurred_at: string;
    notes: string | null;
    download_url: string;
    facts: Array<{
      id: string;
      document_id: string;
      field_key: string;
      value_text: string;
      source_page: number | null;
      source_excerpt: string | null;
      extraction_method: string;
      status: string;
      confidence_score: number | null;
      reviewed_by_name: string | null;
      reviewed_at: string | null;
      created_at: string;
    }>;
  }>;
  parties: Array<{
    id: string;
    party_type: string;
    name: string;
    company_name: string | null;
    email: string | null;
    phone: string | null;
    address: string | null;
    is_primary: boolean;
    notes: string | null;
    created_at: string;
  }>;
  checklist: Array<{
    id: string;
    item_key: string | null;
    category: string;
    title: string;
    description: string | null;
    status: string;
    is_required: boolean;
    responsible_user_id: string | null;
    responsible_name: string | null;
    due_at: string | null;
    completed_at: string | null;
    dependency_item_id: string | null;
    evidence_document_id: string | null;
    evidence_notes: string | null;
    escalated_at: string | null;
    sort_order: number;
  }>;
  events: Array<{
    id: string;
    event_type: string;
    summary: string;
    actor_name: string | null;
    occurred_at: string;
  }>;
};

export type TransactionCopilotRecommendation = {
  id: string;
  transaction_id: string;
  lead_id: string;
  ai_run_log_id: string | null;
  status: string;
  output_payload: {
    status_summary: string;
    missing_items: string[];
    deadline_risks: Array<{
      item: string;
      due_at: string;
      severity: "info" | "warning" | "critical";
      reason: string;
      evidence: string[];
    }>;
    document_findings: Array<{
      finding: string;
      document_id: string | null;
      source_page: number | null;
      evidence: string;
    }>;
    party_gaps: string[];
    recommended_internal_actions: string[];
    closing_attorney_email_draft: string;
    seller_email_draft: string;
    legal_escalations: string[];
    evidence: string[];
    confidence: number;
  };
  confidence_score: number | null;
  generated_at: string;
  reviewed_at: string | null;
};

export type TransactionCopilotOverview = {
  pilot_mode: "draft_only";
  runtime_status: string;
  capability_status: string;
  external_actions_blocked: boolean;
  readiness_score: number;
  readiness_band: "ready" | "needs_review" | "blocked";
  readiness_gaps: string[];
  deadline_risks: Array<{
    item: string;
    due_at: string;
    severity: "info" | "warning" | "critical";
    reason: string;
    evidence: string[];
  }>;
  evidence_available: string[];
  confirmed_document_fact_count: number;
  recommendations: TransactionCopilotRecommendation[];
  metrics: {
    generated: number;
    reviewed: number;
    accepted_or_corrected_rate_basis_points: number;
    correction_rate_basis_points: number;
    estimated_time_saved_minutes: number;
  };
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
    console.warn("Clerk token unavailable: NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing.");
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

export async function getWorkspaceProfile(): Promise<WorkspaceProfile | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/me`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    const profile = (await response.json()) as Partial<WorkspaceProfile>;
    if (
      typeof profile.user_id !== "string" ||
      typeof profile.organization_id !== "string" ||
      typeof profile.email !== "string" ||
      typeof profile.display_name !== "string" ||
      !Array.isArray(profile.role_keys) ||
      !Array.isArray(profile.permissions) ||
      typeof profile.unread_notification_count !== "number"
    ) {
      return null;
    }
    return profile as WorkspaceProfile;
  } catch (error) {
    if (
      !(error instanceof Error) ||
      !error.message.includes("Dynamic server usage")
    ) {
      console.error("Stonegate workspace profile verification failed.", error);
    }
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

export async function getUnderwritingCalibration(): Promise<{
  calibration: UnderwritingCalibration | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/underwriting/calibration`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      calibration: (await response.json()) as UnderwritingCalibration,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate underwriting calibration request failed.", error);
    return { calibration: null, apiConnected: false };
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

export async function getAcquisitionOperations(): Promise<{
  operations: AcquisitionOperations | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/operations`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      operations: (await response.json()) as AcquisitionOperations,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate acquisition operations request failed.", error);
    return { operations: null, apiConnected: false };
  }
}

export async function getOperatingModelOverview(): Promise<{
  operatingModel: OperatingModelOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/operating-model`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      operatingModel: (await response.json()) as OperatingModelOverview,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate operating model request failed.", error);
    return { operatingModel: null, apiConnected: false };
  }
}

export async function getCampaignManagementOverview(): Promise<{
  campaignManagement: CampaignManagementOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/campaign-management`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      campaignManagement: (await response.json()) as CampaignManagementOverview,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate campaign management request failed.", error);
    return { campaignManagement: null, apiConnected: false };
  }
}

export async function getProspectingWorkbench(): Promise<{
  prospecting: ProspectingWorkbenchOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/prospecting`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      prospecting: (await response.json()) as ProspectingWorkbenchOverview,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate prospecting workbench request failed.", error);
    return { prospecting: null, apiConnected: false };
  }
}

export async function getLeadManagerOverview(): Promise<{
  leadManager: LeadManagerOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/lead-manager`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      leadManager: (await response.json()) as LeadManagerOverview,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate Lead Manager request failed.", error);
    return { leadManager: null, apiConnected: false };
  }
}

export async function getFieldOperationsOverview(): Promise<{
  fieldOperations: FieldOperationsOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/field-operations`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      fieldOperations: (await response.json()) as FieldOperationsOverview,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate field operations request failed.", error);
    return { fieldOperations: null, apiConnected: false };
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
  period_days: null,
  period_start_at: null,
  period_end_at: new Date(0).toISOString(),
  previous_summary: null,
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

export async function getFinanceOverview(periodDays?: number): Promise<{
  finance: FinanceOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const query = periodDays ? `?period_days=${periodDays}` : "";
    const response = await fetch(`${apiBaseUrl}/api/v1/finance${query}`, {
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
  period_days: null,
  period_start_at: null,
  period_end_at: new Date(0).toISOString(),
  previous_summary: null,
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
  public_funnel: {
    page_views: 0,
    offer_starts: 0,
    form_starts: 0,
    step_completions: {},
    validation_errors: 0,
    submit_attempts: 0,
    form_submits: 0,
    submit_errors: 0,
    form_abandons: 0,
    start_to_submit_rate_basis_points: null,
  },
  web_vitals: [],
  campaigns: [],
  offline_exports: [],
};

export async function getMarketingOverview(periodDays?: number): Promise<{
  marketing: MarketingOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const query = periodDays ? `?period_days=${periodDays}` : "";
    const response = await fetch(`${apiBaseUrl}/api/v1/marketing${query}`, {
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
    total_cost_microusd: 0,
    unpriced_run_count: 0,
    average_latency_ms: null,
  },
  call_intelligence_quality: {
    total_calls: 0,
    reviewed_calls: 0,
    approved_calls: 0,
    rejected_calls: 0,
    pending_review_calls: 0,
    failed_calls: 0,
    average_confidence: null,
    average_field_agreement: null,
    average_evidence_coverage: null,
    high_correction_calls: 0,
    minimum_review_sample: 50,
    autonomy_status: "human_review_required",
    autonomy_blockers: ["No reviewed call sample is available."],
  },
  agents: [],
  prompt_versions: [],
  runs: [],
  orchestrator: {
    metrics: {
      portfolio_agent_count: 0,
      copilot_count: 0,
      active_copilot_count: 0,
      governed_run_count: 0,
      unreviewed_trace_count: 0,
      approved_dataset_count: 0,
      passing_evaluation_count: 0,
      pending_promotion_count: 0,
      active_promotion_count: 0,
      budget_blocked_run_count: 0,
    },
    foundation: {
      status: "not_installed",
      copilots: [],
      data_governance_policies: [],
      knowledge_sources: [],
      data_quality_rules: [],
    },
    events: [],
    datasets: [],
    evaluation_runs: [],
    promotions: [],
    runtime: {
      status: "not_installed",
      policy: null,
      capabilities: [],
      comparisons: [],
      metrics: {
        enabled_capability_count: 0,
        blocked_run_count: 0,
        failed_run_count: 0,
        redacted_trace_count: 0,
        knowledge_use_count: 0,
        regression_block_count: 0,
      },
    },
  },
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

export async function getTransactionOverview(): Promise<{
  transactions: TransactionOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/transactions`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      transactions: (await response.json()) as TransactionOverview,
      apiConnected: true,
    };
  } catch {
    return { transactions: null, apiConnected: false };
  }
}

export async function getDispositionOverview(): Promise<{
  dispositions: DispositionOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/dispositions`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      dispositions: (await response.json()) as DispositionOverview,
      apiConnected: true,
    };
  } catch {
    return { dispositions: null, apiConnected: false };
  }
}
