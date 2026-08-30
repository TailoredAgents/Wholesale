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

export type IntegrationStatus = {
  key: string;
  name: string;
  category: string;
  mode: string;
  enabled: boolean;
  configured: boolean;
  blockers: string[];
  runtime_status?: string | null;
  last_success_at?: string | null;
  details?: string[];
};

export type LeadListItem = {
  id: string;
  source: string;
  asset_class: "house" | "land";
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
  property_parcel_id: string | null;
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
  assigned_user_id: string | null;
  assigned_user_email: string | null;
  motivation: string | null;
  desired_timeline: string | null;
  property_condition: string | null;
  occupancy_status: string | null;
  asking_price: string | null;
  mortgage_balance: string | null;
  appointment_status: string | null;
  qualification_context: Record<string, unknown>;
  next_follow_up_at: string | null;
  primary_next_action: {
    task_id: string;
    title: string;
    action_type: string;
    due_at: string | null;
    responsible_user_id: string | null;
    responsible_user_email: string | null;
    due_status: string;
  } | null;
  archived_at: string | null;
  close_out_disposition: "dead" | "disqualified" | null;
  close_out_reason: string | null;
  closed_out_at: string | null;
  closed_out_by_user_id: string | null;
  closed_out_by_user_email: string | null;
  created_at: string;
};

export type LeadCloseOutResponse = {
  lead: LeadListItem;
  changed: boolean;
  cancelled_tasks: number;
  cancelled_appointments: number;
  cancelled_follow_up_enrollments: number;
  cancelled_follow_up_approvals: number;
  cancelled_pending_approvals: number;
  completed_calling_list_entries: number;
  dismissed_ai_next_action_events: number;
  dismissed_notifications: number;
  closed_lead_management_case: boolean;
  closed_conversation: boolean;
};

export type LeadReopenResponse = {
  lead: LeadListItem;
  changed: boolean;
  follow_up_task_id: string;
};

export type OperationsUser = {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  calling_enabled: boolean;
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
    asset_class: "house" | "land";
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
    asset_class: "house" | "land";
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
  company_setup: CompanySetup;
};

export type OperatingSeat = {
  id: string;
  seat_key: string;
  label: string;
  role_key: string;
  status: string;
  primary_user_id: string | null;
  primary_user_name: string | null;
  backup_user_id: string | null;
  backup_user_name: string | null;
  notes: string | null;
};

export type BusinessCounterparty = {
  id: string;
  market_id: string | null;
  market_name: string | null;
  counterparty_type: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  status: string;
  verified_by_user_id: string | null;
  verified_by_name: string | null;
  verified_at: string | null;
  notes: string | null;
};

export type StaffRoleAcceptance = {
  id: string;
  user_id: string;
  user_name: string;
  role_key: string;
  manual_key: string;
  manual_version: string;
  status: string;
  assigned_by_user_id: string;
  assigned_by_name: string;
  workspace_test_evidence: string | null;
  employee_notes: string | null;
  accepted_at: string | null;
  approved_by_user_id: string | null;
  approved_by_name: string | null;
  manager_notes: string | null;
  approved_at: string | null;
};

export type CompanySetup = {
  seats: OperatingSeat[];
  counterparties: BusinessCounterparty[];
  role_acceptances: StaffRoleAcceptance[];
  checks: Array<{
    key: string;
    label: string;
    status: "complete" | "attention" | "not_started";
    detail: string;
  }>;
  completed_check_count: number;
  total_check_count: number;
};

export type MyRoleSetup = {
  user_id: string;
  user_name: string;
  role_keys: string[];
  acceptances: StaffRoleAcceptance[];
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
    cohort_id: string | null;
    cohort_name: string | null;
    mapping_id: string;
    mapping_name: string;
    default_assignee_user_id: string | null;
    default_assignee_name: string | null;
    imported_by_user_id: string;
    imported_by_name: string;
    file_name: string;
    file_sha256: string;
    source_name: string;
    source_profile: string;
    source_export_id: string | null;
    source_list_id: string | null;
    source_list_name: string | null;
    source_exported_at: string | null;
    source_filters: Record<string, unknown>;
    status: string;
    total_rows: number;
    valid_rows: number;
    imported_rows: number;
    matched_existing_rows: number;
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
      source_membership_id: string | null;
      relationship_state: string;
      contact_point_count: number;
      legal_name: string | null;
      phone: string | null;
      property_address: string | null;
      validation_errors: string[];
      eligibility_reasons: string[];
    }>;
  }>;
  source_memberships: Array<{
    id: string;
    prospect_id: string;
    legal_name: string;
    campaign_id: string;
    campaign_name: string;
    cohort_id: string | null;
    cohort_name: string | null;
    source_name: string;
    source_profile: string;
    source_record_key: string | null;
    source_list_key: string;
    source_list_name: string | null;
    first_import_batch_id: string;
    latest_import_batch_id: string;
    first_seen_at: string;
    last_seen_at: string;
    appearance_count: number;
    relationship_state_at_latest_import: string;
    source_metadata: Record<string, unknown>;
  }>;
  contact_points: Array<{
    id: string;
    prospect_id: string;
    legal_name: string;
    source_membership_id: string | null;
    contact_type: string;
    value: string;
    normalized_value: string;
    rank: number;
    is_primary: boolean;
    validation_status: string;
    contact_metadata: Record<string, unknown>;
    first_seen_at: string;
    last_seen_at: string;
  }>;
  cohorts: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    script_version_id: string | null;
    created_by_user_id: string;
    created_by_name: string;
    name: string;
    code: string;
    status: string;
    source_name: string;
    list_type: string;
    market_label: string;
    dialer_mode: "one_line_power";
    call_window_start_hour: number;
    call_window_end_hour: number;
    timezone: string;
    starts_on: string;
    ends_on: string | null;
    cohort_metadata: Record<string, unknown>;
    created_at: string;
  }>;
  work_sessions: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    cohort_id: string;
    cohort_name: string;
    caller_user_id: string;
    caller_name: string;
    campaign_cost_id: string;
    work_date: string;
    paid_minutes: number;
    productive_calling_minutes: number;
    utilization_rate_basis_points: number;
    hourly_rate_cents: number;
    labor_cost_cents: number;
    source: string;
    provider_session_id: string | null;
    notes: string | null;
    created_at: string;
  }>;
  costs: Array<{
    id: string;
    campaign_id: string;
    campaign_name: string;
    cohort_id: string | null;
    cohort_name: string | null;
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
    cohort_id: string | null;
    cohort_name: string | null;
    dialer_mode: string;
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
    submitted_handoffs: number;
    accepted_warm_leads: number;
    rejected_handoffs: number;
    invalid_rows: number;
    duplicate_rows: number;
    suppressed_rows: number;
    bad_data_rate_basis_points: number;
    duplicate_rate_basis_points: number;
    conversion_rate_basis_points: number;
    cost_per_imported_prospect_cents: number | null;
    cost_per_callable_prospect_cents: number | null;
    cost_per_accepted_warm_lead_cents: number | null;
    calling_batch_entries: number;
    calling_batch_completed: number;
  }>;
};

export type ProspectingScript = {
  id: string;
  version_number: number;
  asset_class: "house" | "land";
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

export type ProspectingQualificationState =
  | "not_covered"
  | "answered"
  | "needs_follow_up"
  | "conflict";

export type ProspectingQualificationChecklistItem = {
  question_key: string;
  label: string;
  prompt: string;
  answer_type: "text" | "choice";
  choices: string[];
  is_required: boolean;
  state: ProspectingQualificationState;
  answer_value: string | null;
  source: string;
  revision: number;
  captured_at: string | null;
  updated_at: string | null;
  blockers?: string[];
};

export type ProspectingSellerOutcome =
  | "no_answer"
  | "left_voicemail"
  | "callback_requested"
  | "follow_up"
  | "interested"
  | "appointment_set"
  | "not_interested"
  | "wrong_number"
  | "do_not_call";

export type ProspectingAttemptCompletionPayload = {
  outcome: ProspectingSellerOutcome;
  idempotency_key: string;
  browser_session_id: string | null;
  lease_token: string | null;
  qualification_answers: Record<string, never>;
  notes: string | null;
  callback_at: string | null;
  handoff_user_id: string | null;
  appointment_start_at: string | null;
  appointment_location_type: "phone" | "video" | "seller_property" | "office" | null;
  appointment_location: string | null;
  compliance_flags: string[];
};

export type ProspectingTechnicalFailurePayload = {
  idempotency_key: string;
  browser_session_id: string;
  lease_token: string;
};

export type ProspectingQualificationChecklist = {
  attempt_id: string;
  script_version_id: string;
  items: ProspectingQualificationChecklistItem[];
  answered_count: number;
  total_count: number;
  required_answered_count: number;
  required_count: number;
  missing_required_keys: string[];
  complete: boolean;
};

export type ProspectingAttempt = {
  id: string;
  script_version_id: string;
  script_version_number: number;
  cohort_id: string | null;
  dialer_mode: string;
  status: string;
  outcome: string | null;
  contact_made: boolean | null;
  answer_classification: string;
  party_classification: string;
  interest_classification: string;
  follow_up_permission: string;
  classification_source: string;
  dial_started_at: string | null;
  answered_at: string | null;
  right_party_confirmed_at: string | null;
  interest_confirmed_at: string | null;
  measurement_metadata: Record<string, unknown>;
  qualification_checklist: ProspectingQualificationChecklist;
  qualification_answers: Record<string, string>;
  notes: string | null;
  callback_at: string | null;
  started_at: string;
  completed_at: string | null;
  quality_score_basis_points: number | null;
};

export type ProspectingCallNoteEvidence = {
  field: string;
  segment_index: number;
  start_seconds: number;
  supporting_text: string;
};

export type ProspectingStructuredCallNotes = {
  summary: string;
  motivation: string | null;
  timeline: string | null;
  property_condition: string | null;
  occupancy_status: string | null;
  asking_price: string | null;
  mortgage_balance: string | null;
  mortgage_or_title: string | null;
  repairs: string[];
  objections: string[];
  commitments: string[];
  next_action: string | null;
  follow_up_at: string | null;
  appointment_details: string | null;
  confidence: number;
  evidence: ProspectingCallNoteEvidence[];
  parcel_id?: string | null;
  acreage?: string | null;
  legal_description?: string | null;
  access_or_frontage?: string | null;
  utilities?: string | null;
  zoning_or_use?: string | null;
  septic_or_perc?: string | null;
  taxes_or_hoa?: string | null;
  terrain_or_environmental_concerns?: string | null;
};

export type ProspectingVoiceRecording = {
  id: string;
  call_record_id: string;
  status: string;
  duration_seconds: number | null;
  channel_count: number | null;
  consent_status: string;
  recorded_at: string | null;
  retention_expires_at: string | null;
  deleted_at: string | null;
  deletion_reason: string | null;
};

export type ProspectingCallTranscript = {
  id: string;
  status: string;
  model_name: string | null;
  language: string | null;
  transcript_text: string | null;
  speaker_segments: Array<{
    index?: number;
    speaker?: string;
    start?: number;
    end?: number;
    text?: string;
  }>;
  confidence_score: number | null;
  structured_notes: ProspectingStructuredCallNotes | null;
  quick_read_summary: string | null;
  approval_request_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  error_message: string | null;
};

export type ProspectingAttemptEvidenceStatus =
  | "unavailable"
  | "recording_ready"
  | "processing"
  | "ready"
  | "failed"
  | "exhausted";

export type ProspectingAttemptEvidenceSuggestion = {
  question_key: string;
  state: "suggested" | "corroborated" | "conflict";
  current_value: unknown | null;
  suggested_value: unknown;
  evidence: ProspectingCallNoteEvidence[];
};

export type ProspectingAttemptEvidence = {
  attempt_id: string;
  call_record_id: string | null;
  dial_leg_id: string | null;
  recording: ProspectingVoiceRecording | null;
  transcript: ProspectingCallTranscript | null;
  suggestions: ProspectingAttemptEvidenceSuggestion[];
  capabilities: {
    can_play: boolean;
    can_download_audio: boolean;
    can_download_transcript: boolean;
    can_retry: boolean;
    can_delete: boolean;
  };
  evidence_status: ProspectingAttemptEvidenceStatus;
};

export type ProspectingEntry = {
  id: string;
  batch_id: string;
  batch_name: string;
  campaign_id: string;
  cohort_id: string | null;
  cohort_name: string | null;
  campaign_name: string;
  asset_class: "house" | "land";
  script: ProspectingScript | null;
  source_name: string;
  warnings: string[];
  assigned_user_id: string;
  assigned_user_name: string;
  prospect_id: string;
  legal_name: string;
  phone: string | null;
  email: string | null;
  contact_points: Array<{
    contact_type: string;
    value: string;
    rank: number;
    is_primary: boolean;
    validation_status: string;
  }>;
  property_address: string | null;
  sequence_number: number;
  status: string;
  queue_kind: string;
  is_actionable: boolean;
  dialer_mode: string;
  provider_sync_status: string;
  attempt_count: number;
  disposition: string | null;
  next_attempt_at: string | null;
  active_attempt: ProspectingAttempt | null;
  attempts: ProspectingAttempt[];
};

export type ProspectingDialerProfile = {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  user_is_active: boolean;
  user_calling_enabled: boolean;
  voice_line_id: string | null;
  voice_line_label: string | null;
  voice_line_number: string | null;
  status: "inactive" | "active" | "suspended";
  default_line_count: number;
  max_line_count: number;
  effective_line_count: number;
  recording_policy: string;
  daily_dial_limit: number | null;
  daily_spend_limit_cents: number | null;
};

export type ProspectingDialSession = {
  id: string;
  caller_user_id: string;
  campaign_id: string;
  cohort_id: string | null;
  prospect_calling_batch_id: string | null;
  voice_line_id: string | null;
  current_prospect_id: string | null;
  current_batch_entry_id: string | null;
  current_attempt_id: string | null;
  state:
    | "ready"
    | "dialing"
    | "ringing"
    | "connected"
    | "wrap_up"
    | "paused"
    | "reconnecting"
    | "ended"
    | "stopped"
    | "failed"
    | "expired";
  requested_line_count: number;
  effective_line_count: number;
  organization_line_limit: number;
  va_line_limit: number;
  campaign_line_limit: number;
  voice_line_limit: number;
  feature_line_limit: number;
  pause_after_current: boolean;
  stop_after_current: boolean;
  lease_expires_at: string | null;
  started_at: string;
  paused_at: string | null;
  resumed_at: string | null;
  heartbeat_at: string;
  ended_at: string | null;
  stop_reason: string | null;
};

export type ProspectingDialLeg = {
  id: string;
  dial_session_id: string;
  prospect_id: string;
  batch_entry_id: string;
  attempt_id: string | null;
  contact_point_id: string | null;
  voice_line_id: string | null;
  call_record_id: string | null;
  line_slot: number;
  recipient: string;
  provider: string;
  provider_call_id: string | null;
  status:
    | "queued"
    | "dialing"
    | "ringing"
    | "answered"
    | "connected"
    | "cancelling"
    | "cancelled"
    | "no_answer"
    | "busy"
    | "failed"
    | "completed";
  queued_at: string;
  dialing_at: string | null;
  ringing_at: string | null;
  answered_at: string | null;
  connected_at: string | null;
  cancelled_at: string | null;
  failed_at: string | null;
  completed_at: string | null;
  answer_classification: string;
  party_classification: string;
  terminal_result: string | null;
  provider_error_code: string | null;
  provider_error_message: string | null;
  cancellation_reason: string | null;
};

export type ProspectingDialSessionSnapshot = {
  session: ProspectingDialSession;
  current_leg: ProspectingDialLeg | null;
};

export type ProspectingDialSessionControl = {
  snapshot: ProspectingDialSessionSnapshot;
  lease_token: string | null;
  queue_status: "reserved" | "unchanged" | "empty" | "none";
  replayed: boolean;
};

export type ProspectingDialerContext = {
  feature_enabled: boolean;
  configured_line_cap: number;
  implemented_line_cap: number;
  effective_line_cap: number;
  can_manage: boolean;
  profile: ProspectingDialerProfile | null;
  active_session: ProspectingDialSession | null;
  active_legs: ProspectingDialLeg[];
  blockers: string[];
};

export type ProspectingInboundCallback = {
  id: string;
  voice_line_id: string;
  voice_line_label: string;
  caller_number: string;
  match_status: "pending" | "matched" | "unknown" | "ambiguous";
  match_strategy: string;
  match_confidence_basis_points: number;
  candidate_count: number;
  matched_prospect_id: string | null;
  matched_attempt_id: string | null;
  batch_entry_id: string | null;
  can_open: boolean;
  prospect_name: string | null;
  property_address: string | null;
  assigned_user_id: string | null;
  assigned_user_name: string | null;
  fallback_user_id: string | null;
  status:
    | "received"
    | "routing"
    | "ringing"
    | "answered"
    | "voicemail"
    | "missed"
    | "completed"
    | "failed"
    | "canceled";
  call_record_id: string | null;
  missed_task_id: string | null;
  received_at: string;
  answered_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ProspectingInboundCallbackList = {
  items: ProspectingInboundCallback[];
  total: number;
};

export type ProspectingDialerOperations = {
  feature_enabled: boolean;
  company_enabled: boolean;
  configured_line_cap: number;
  implemented_line_cap: number;
  effective_line_cap: number;
  callers: Array<{
    id: string;
    display_name: string;
    email: string;
    is_active: boolean;
    calling_enabled: boolean;
  }>;
  profiles: ProspectingDialerProfile[];
  eligible_lines: Array<{
    id: string;
    label: string;
    phone_number: string;
    status: string;
    assigned_user_id: string | null;
    fallback_user_id: string | null;
    assigned_team_id: string | null;
    ring_strategy: string;
    missed_call_action: string;
    max_concurrent_legs: number;
  }>;
  campaigns: Array<{
    id: string;
    name: string;
    code: string;
    status: string;
    enabled: boolean;
    max_concurrent_legs: number;
  }>;
  sessions: Array<{
    session: ProspectingDialSession;
    caller_name: string;
    caller_email: string;
    campaign_name: string;
    voice_line_label: string | null;
    current_leg_status: string | null;
    health_status: "healthy" | "stale" | "reconnecting" | "attention";
  }>;
  health: {
    active_session_count: number;
    stale_session_count: number;
    reconnecting_session_count: number;
    active_leg_count: number;
    callback_waiting_count: number;
    missed_callback_task_count: number;
    open_recovery_failure_count: number;
    oldest_heartbeat_at: string | null;
    worker_status: string;
    worker_heartbeat_at: string | null;
  };
  recent_errors: Array<{
    occurred_at: string;
    code: string;
    message: string;
    session_id: string | null;
    caller_user_id: string | null;
    campaign_id: string | null;
    recoverable: boolean;
  }>;
};

export type ProspectingDialerPilotGate = {
  key: string;
  label: string;
  status: "pass" | "warning" | "block" | "pending";
  detail: string;
};

export type ProspectingDialerPilotAttempt = {
  attempt_id: string;
  dial_session_id: string;
  acceptance_stage: "smoke_testing" | "running" | "accepted" | null;
  counts_toward_production_shift: boolean;
  started_at: string;
  completed_at: string | null;
  outcome: string | null;
  review_status: "pending" | "passed" | "failed";
  blocker: string | null;
  call_record_ids: string[];
  provider_call_ids: string[];
  placed_call: boolean;
  smoke_test_eligible: boolean;
};

export type ProspectingDialerPilotShift = {
  id: string;
  dial_session_id: string;
  shift_date: string;
  timezone: string;
  status: "pending" | "passed" | "failed";
  server_attempt_count: number;
  server_reviewed_attempt_count: number;
  server_passed_attempt_count: number;
  reserved_attempt_count: number;
  provider_started_attempt_count: number;
  placed_call_count: number;
  productive_minutes: number;
  all_attempts_reviewed: boolean;
  all_legs_terminal: boolean;
  no_duplicate_calls: boolean;
  no_lost_answers: boolean;
  no_stuck_sessions: boolean;
  callbacks_reconciled: boolean;
  handoffs_reconciled: boolean;
  provider_billing_verified: boolean;
  daily_caps_respected: boolean;
  kill_switches_verified: boolean;
  recordings_reviewed: boolean;
  compliance_clear: boolean;
  reviewed_at: string;
  reason: string;
};

export type ProspectingDialerPilotAttemptReview = {
  id: string;
  attempt_id: string;
  dial_session_id: string;
  status: "pending" | "passed" | "failed";
  server_dial_leg_count: number;
  server_terminal_leg_count: number;
  disposition_complete: boolean;
  recording_review_required: boolean;
  recording_reviewed: boolean;
  callback_required: boolean;
  callback_reconciled: boolean;
  handoff_required: boolean;
  handoff_reconciled: boolean;
  provider_cost_verified: boolean;
  compliance_clear: boolean;
  reviewed_at: string;
  reason: string;
};

export type ProspectingDialerPilotRecord = {
  id: string;
  revision: number;
  status: "draft" | "smoke_testing" | "running" | "ready_for_owner_review" | "accepted" | "rejected" | "rolled_back" | "revoked" | "cancelled";
  caller_user_id: string;
  caller_name: string;
  campaign_id: string;
  campaign_name: string;
  cohort_id: string;
  cohort_name: string;
  prospect_calling_batch_id: string;
  calling_batch_name: string;
  voice_line_id: string;
  voice_line_number: string;
  effective_line_count: number;
  timezone: string;
  daily_dial_limit: number;
  daily_spend_limit_cents: number;
  required_clean_shift_count: number;
  minimum_attempts_per_shift: number;
  minimum_productive_minutes_per_shift: number;
  minimum_total_attempts: number;
  minimum_batch_size: number;
  maximum_batch_size: number;
  configuration_fingerprint: string;
  smoke_test_evidence: Record<string, unknown>;
  kill_switch_evidence: Record<string, unknown>;
  batchdialer_comparison_evidence: Record<string, unknown>;
  rollback_evidence: Record<string, unknown>;
  start_attestation: Record<string, unknown>;
  evidence_hash: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  submitted_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  rolled_back_at: string | null;
  revoked_at: string | null;
  revocation_reason: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
};

export type ProspectingDialerPilotOverview = {
  pilot: ProspectingDialerPilotRecord | null;
  gates: ProspectingDialerPilotGate[];
  attempt_review_queue: ProspectingDialerPilotAttempt[];
  attempt_reviews: ProspectingDialerPilotAttemptReview[];
  shift_reviews: ProspectingDialerPilotShift[];
  current_configuration_fingerprint: string | null;
  configuration_matches: boolean;
  batch_entry_count: number;
  total_reviewed_attempts: number;
  total_passed_attempts: number;
  passed_shift_count: number;
  allowed_actions: string[];
};

export type ProspectingDialerAnalyticsCoverage = {
  raw_attempts_basis_points: number | null;
  paid_hours_basis_points: number | null;
  provider_cost_basis_points: number | null;
  appointment_outcomes_basis_points: number | null;
  profit_basis_points: number | null;
  reputation_basis_points: number | null;
  warnings: string[];
};

export type ProspectingDialerScorecardMetrics = {
  entered_leads: number;
  attempts: number | null;
  answered_calls: number | null;
  human_conversations: number | null;
  conversations_over_60_seconds: number | null;
  right_party_contacts: number | null;
  qualified_sellers: number | null;
  appointments_set: number | null;
  appointments_held: number | null;
  submitted_handoffs: number | null;
  accepted_handoffs: number | null;
  signed_contracts: number | null;
  closed_assignments: number | null;
  paid_minutes: number | null;
  productive_calling_minutes: number | null;
  labor_cost_cents: number | null;
  provider_cost_cents: number | null;
  list_cost_cents: number | null;
  other_cost_cents: number | null;
  total_cost_cents: number | null;
  gross_revenue_cents: number | null;
  contribution_profit_cents: number | null;
  attempts_per_paid_hour_x100: number | null;
  human_conversations_per_paid_hour_x100: number | null;
  profit_per_paid_hour_cents: number | null;
  cost_per_qualified_seller_cents: number | null;
  cost_per_contract_cents: number | null;
  human_contact_rate_basis_points: number | null;
  right_party_contact_rate_basis_points: number | null;
  qualified_seller_rate_basis_points: number | null;
  accepted_handoff_rate_basis_points: number | null;
  appointment_held_rate_basis_points: number | null;
  contract_rate_basis_points: number | null;
  close_rate_basis_points: number | null;
  short_calls: number | null;
  silent_or_dead_air_calls: number | null;
  blocked_or_failed_calls: number | null;
  no_answer_calls: number | null;
  voicemail_calls: number | null;
  duplicate_call_incidents: number | null;
  seller_complaints: number | null;
  dnc_requests: number | null;
  abandoned_calls: number | null;
  average_connection_time_seconds: number | null;
  number_reputation_score: number | null;
  answer_rate_trend_basis_points: number | null;
  coverage: ProspectingDialerAnalyticsCoverage;
  status_by_key?: Record<
    string,
    "known" | "partial" | "unknown" | "not_applicable"
  >;
};

export type ProspectingDialerDimensionScorecard = {
  dimension_type: "va" | "campaign" | "cohort" | "list" | "dial_mode" | "source";
  dimension_id: string | null;
  dimension_name: string;
  source: string | null;
  dial_mode: string | null;
  entry_stage?: string | null;
  external_key?: string | null;
  metrics: ProspectingDialerScorecardMetrics;
};

export type ProspectingDialerAnalytics = {
  period: {
    date_from: string;
    date_to: string;
    timezone: "UTC";
    start_at: string;
    end_at_exclusive: string;
    report_mode?: "activity_window";
    as_of?: string;
  };
  filters: {
    cohort_id: string | null;
    source: string | null;
    campaign_id: string | null;
    caller_user_id: string | null;
    dial_mode: string | null;
  };
  filter_options: {
    sources: string[];
    campaigns: Array<{ id: string; name: string }>;
    cohorts: Array<{ id: string; name: string }>;
    callers: Array<{ id: string; name: string }>;
    dial_modes: string[];
  };
  summary: ProspectingDialerScorecardMetrics;
  by_va: ProspectingDialerDimensionScorecard[];
  by_campaign: ProspectingDialerDimensionScorecard[];
  by_cohort: ProspectingDialerDimensionScorecard[];
  by_list: ProspectingDialerDimensionScorecard[];
  by_dial_mode: ProspectingDialerDimensionScorecard[];
  by_source: ProspectingDialerDimensionScorecard[];
  daily_trend: Array<{
    date: string;
    attempts: number | null;
    human_conversations: number | null;
    right_party_contacts: number | null;
    accepted_handoffs: number | null;
    answer_rate_basis_points: number | null;
    blocked_or_failed_calls: number | null;
  }>;
  readiness: {
    status: "blocked" | "needs_review" | "ready_for_controlled_pilot";
    controlled_pilot_ready: boolean;
    d10_acceptance_required: true;
    observed_at?: string;
    checks: Array<{
      key: string;
      label: string;
      status: "pass" | "warning" | "block";
      detail: string;
    }>;
    blockers: string[];
    warnings: string[];
  };
  metric_definitions: Array<{
    key: string;
    label: string;
    definition: string;
    source_records: string[];
    attribution_timestamp: string;
    unavailable_when: string | null;
  }>;
  attribution_model_version?: string;
  profit_formula_version?: string;
  financials_visible?: boolean;
};

export type ProspectingDialerAnalyticsQuery = {
  date_from?: string;
  date_to?: string;
  cohort_id?: string;
  source?: string;
  campaign_id?: string;
  caller_user_id?: string;
  dial_mode?: string;
};

export type BatchDialerVaPerformanceMetrics = {
  calls: number | null;
  unique_contacts: number | null;
  identified_contact_calls: number | null;
  identified_contact_coverage_basis_points: number | null;
  human_contacts: number | null;
  recorded_duration_calls: number | null;
  recorded_duration_coverage_basis_points: number | null;
  recorded_call_seconds: number | null;
  average_recorded_call_seconds: number | null;
  qualified_candidates: number | null;
  evidence_accepted_candidates: number | null;
  verified_handoffs: number | null;
  qualification_false_positives: number | null;
  appointments_set: number | null;
  appointments_entered: number | null;
  handoffs_with_appointment_entered: number | null;
  appointments_held: number | null;
  signed_contracts: number | null;
  closed_transactions: number | null;
  dnc: number | null;
  not_interested: number | null;
  voicemails: number | null;
  no_answers: number | null;
  first_call_at: string | null;
  last_call_at: string | null;
  inferred_calling_minutes: number | null;
  human_contact_rate_basis_points: number | null;
  evidence_acceptance_rate_basis_points: number | null;
  false_positive_rate_basis_points: number | null;
  appointments_entered_rate_basis_points: number | null;
};

export type BatchDialerVaPerformanceAgent = {
  mapping_id: string | null;
  provider_agent_id: string;
  provider_agent_name: string;
  user_id: string | null;
  user_name: string | null;
  metrics: BatchDialerVaPerformanceMetrics;
};

export type BatchDialerVaPerformanceCampaign = {
  provider_campaign_id: string;
  campaign_name: string;
  metrics: BatchDialerVaPerformanceMetrics;
};

export type BatchDialerVaPerformanceDailyActivity = {
  date: string;
  provider_agent_id: string;
  provider_agent_name: string;
  metrics: BatchDialerVaPerformanceMetrics;
};

export type BatchDialerVaPerformanceHourlyActivity = {
  hour_start_at: string;
  provider_agent_id: string;
  provider_agent_name: string;
  calls: number | null;
  human_contacts: number | null;
  verified_handoffs: number | null;
  recorded_call_seconds: number | null;
};

export type BatchDialerVaPerformance = {
  timezone: string;
  date_from: string;
  date_to: string;
  as_of: string;
  earliest_archived_call_at: string | null;
  archive_history_status:
    | "no_archived_calls"
    | "selected_range_may_be_incomplete"
    | "archived_calls_available";
  provider_scan_window_days: number;
  provider_sync_status:
    | "missing"
    | "idle"
    | "polling"
    | "healthy"
    | "failed"
    | "unknown";
  provider_sync_freshness: "current" | "stale" | "incomplete";
  provider_sync_last_success_at: string | null;
  provider_sync_error_present: boolean;
  provider_sync_poll_interval_seconds: number;
  summary: BatchDialerVaPerformanceMetrics;
  agents: BatchDialerVaPerformanceAgent[];
  campaigns: BatchDialerVaPerformanceCampaign[];
  daily_activity: BatchDialerVaPerformanceDailyActivity[];
  hourly_activity: BatchDialerVaPerformanceHourlyActivity[];
  coverage_warnings: string[];
};

export type BatchDialerAgentMapping = {
  id: string;
  provider_agent_id: string;
  provider_agent_name: string;
  user_id: string | null;
  user_name: string | null;
  last_seen_at: string | null;
};

export type BatchDialerAgentMappingUser = {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
};

export type BatchDialerAgentMappings = {
  items: BatchDialerAgentMapping[];
  users: BatchDialerAgentMappingUser[];
};

export type BatchDialerCampaignMapping = {
  id: string;
  provider_campaign_id: string;
  provider_campaign_name: string;
  provider_status: string;
  is_active: boolean;
  asset_class: "house" | "land" | null;
  asset_class_mapped_at: string | null;
  asset_class_mapped_by_user_id: string | null;
  last_seen_at: string;
  historical_lead_count: number;
  historical_asset_mismatch_count: number;
  historical_asset_mismatch_sample_lead_ids: string[];
};

export type BatchDialerCampaignMappings = {
  items: BatchDialerCampaignMapping[];
};

export type BatchDialerCampaignMappingUpdateResponse = {
  item: BatchDialerCampaignMapping;
  requeued_event_count: number;
};

export type BatchDialerVaPerformanceQuery = {
  date_from?: string;
  date_to?: string;
};

export type BatchDialerVaCoachObservation = {
  observation: string;
  evidence_refs: string[];
};

export type BatchDialerVaCoachAction = {
  action: string;
  rationale: string;
  evidence_refs: string[];
};

export type BatchDialerVaCoachCallReview = {
  provider_event_id: string;
  reason: string;
  evidence_refs: string[];
};

export type BatchDialerVaCoachCaveat = {
  caveat: string;
  evidence_refs: string[];
};

export type BatchDialerVaCoachOutput = {
  draft_only: true;
  summary: { text: string; evidence_refs: string[] };
  strengths: BatchDialerVaCoachObservation[];
  concerns: BatchDialerVaCoachObservation[];
  next_shift_actions: BatchDialerVaCoachAction[];
  calls_to_review: BatchDialerVaCoachCallReview[];
  comparison_caveats: BatchDialerVaCoachCaveat[];
  confidence: {
    level: "high" | "medium" | "low";
    rationale: string;
    evidence_refs: string[];
  };
};

export type BatchDialerVaCoachReport = {
  run_id: string;
  provider_agent_id: string;
  range_start: string;
  range_end: string;
  status: string;
  output: BatchDialerVaCoachOutput | null;
  generated_at: string;
  reused: boolean;
  is_stale: boolean;
  refresh_required: boolean;
  stale_reasons: Array<"evidence_changed" | "generation_contract_changed">;
  current_evidence_as_of: string;
};

export type ProspectingVoiceSession = {
  can_initialize: boolean;
  dial_session_id: string;
  identity: string;
  token: string | null;
  expires_at: string | null;
  line: {
    id: string;
    phone_number: string;
    label: string;
    provider: string;
    status: string;
    department_key: string;
    purpose_key: string;
  };
  recording_enabled: boolean;
  effective_line_count: 1;
  blockers: string[];
};

export type ProspectingVoiceCall = {
  context_type: "prospecting";
  call_intent_id: string;
  call_record_id: string;
  prospect_id: string;
  attempt_id: string;
  dial_session_id: string;
  dial_leg_id: string;
  provider: string;
  provider_call_id: string | null;
  provider_status: string;
  recipient: string;
  from_number: string;
  recording_enabled: boolean;
  control_action:
    | "prepared"
    | "started"
    | "fetched"
    | "cancelled"
    | "hung_up"
    | "replayed";
  leg: ProspectingDialLeg;
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
  decision_code: string | null;
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
  queue_entries: ProspectingEntry[];
  queue: {
    ready: number;
    callbacks_due: number;
    callbacks_scheduled: number;
    retries_due?: number;
    retries_scheduled?: number;
    corrections: number;
    in_progress: number;
    handoff_pending: number;
    completed: number;
  };
  batch_queues: Array<{
    batch_id: string;
    batch_name: string;
    campaign_name: string;
    cohort_name: string | null;
    dialer_mode: string;
    provider_sync_status: string;
    ready: number;
    callbacks_due: number;
    callbacks_scheduled: number;
    retries_due?: number;
    retries_scheduled?: number;
    corrections: number;
    in_progress: number;
    handoff_pending: number;
  }>;
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
  asset_class: "house" | "land";
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
  asset_class: "house" | "land";
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

export type AcquisitionsPerformanceDimensionKey =
  | "speed_to_lead"
  | "follow_up_discipline"
  | "conversation_quality"
  | "qualification_quality"
  | "crm_hygiene"
  | "appointment_execution"
  | "mature_outcomes";

export type AcquisitionsPerformanceDimension = {
  key: AcquisitionsPerformanceDimensionKey;
  label: string;
  weight_basis_points: number;
  score: number | null;
  status: "unavailable" | "building" | "ready";
  sample_size: number;
  minimum_sample_size: number;
  numerator: number | null;
  denominator: number | null;
  display_value: string;
  detail: string;
};

export type AcquisitionsPerformanceScorecard = {
  user_id: string;
  user_name: string;
  overall_score: number | null;
  coverage_basis_points: number;
  reliability_status: "building" | "provisional" | "reliable";
  dimensions: AcquisitionsPerformanceDimension[];
  strengths: string[];
  focus_areas: string[];
  warnings: string[];
};

export type AcquisitionsPerformanceOverview = {
  period_days: 30 | 90;
  period_start: string;
  period_end: string;
  policy_version: string;
  shadow_mode: boolean;
  weights: Record<AcquisitionsPerformanceDimensionKey, number>;
  scorecards: AcquisitionsPerformanceScorecard[];
  warnings: string[];
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
  active_scripts: Partial<Record<"house" | "land", LeadManagerQualificationScript>>;
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
    phone_number: string | null;
    county: string | null;
    postal_code: string;
    stage_key: string;
    current_owner_user_id: string | null;
    current_owner_name: string | null;
    next_follow_up_at: string | null;
    lead_url: string;
  }>;
  schedulable_leads: Array<{
    id: string;
    seller_name: string;
    property_address: string;
    phone_number: string | null;
    county: string | null;
    postal_code: string;
    stage_key: string;
    current_owner_user_id: string | null;
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
  estimated_cost_cents: number | null;
  details: string | null;
  scope_status: "unknown" | "no_work" | "repair" | "replace" | "specialist_review";
  severity: "minor" | "standard" | "extensive";
  quantity: number | null;
  unit: string | null;
  pricing_method: "catalog" | "manual" | "contractor";
  manual_override_cents: number | null;
  override_reason: string | null;
  system_low_cents: number | null;
  system_expected_cents: number | null;
  system_high_cents: number | null;
  evidence_source: string;
  evidence_reference: string | null;
  confirmation_status: "unconfirmed" | "user_confirmed" | "walkthrough_verified" | "contractor_verified";
  inspection_status: "not_inspected" | "observed" | "specialist_needed" | "verified";
  catalog_version: string | null;
  uncertainty_note: string | null;
  suggested_by_ai: boolean;
  ai_rationale: string | null;
  ai_confidence: number | null;
  ai_evidence: string[];
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
  updated_at: string;
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
  repair_scenario: Record<string, unknown>;
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
  recommendation_type: "preparation" | "repair_scope" | "follow_up";
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
  repair_scope_capability_status: string;
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
    rejection_rate_basis_points: number;
    blocked_output_count: number;
    average_latency_ms: number | null;
    total_cost_microusd: number;
    estimated_time_saved_minutes: number;
  };
};

export type FieldAppointmentWorkspace = {
  asset_class: "house" | "land";
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
  contract_signing: {
    transaction_id: string | null;
    transaction_status: string | null;
    package_id: string | null;
    package_version: number | null;
    package_status: string | null;
    seller_name: string | null;
    purchase_price_cents: number | null;
    closing_date: string | null;
    agreed_price_cents: number | null;
    ready: boolean;
    blocker: string | null;
    can_send: boolean;
    envelope: EsignEnvelope | null;
  };
  copilot: AcquisitionsCopilotOverview;
  repair_catalog: {
    version: string;
    source_note: string;
    items: Array<{
      category: string;
      label: string;
      unit: string;
      default_quantity: number;
      quantity_basis: string;
    }>;
  };
  can_edit: boolean;
  can_review_underwriting: boolean;
};

export type LandAcquisitionEvidence = {
  value: unknown;
  source_type: "seller_reported" | "provider_sourced" | "crm_record";
  source_name: string;
  observed_at: string | null;
};

export type LandAcquisitionFact = {
  status: "known" | "unknown" | "conflict";
  value: unknown | null;
  source_type: "seller_reported" | "provider_sourced" | "crm_record" | "unknown";
  source_name: string | null;
  observed_at: string | null;
  requires_verification: boolean;
  evidence: LandAcquisitionEvidence[];
};

export type LandAcquisitionProfile = {
  version: "land_acquisition_v1";
  facts: Record<string, LandAcquisitionFact>;
  readiness: {
    status:
      | "ready_for_valuation_review"
      | "needs_seller_information"
      | "needs_due_diligence_review";
    completion_score: number;
    required_fields: string[];
    completed_fields: string[];
    unanswered_fields: string[];
    unknown_fields: string[];
    conflict_fields: string[];
    seller_reported_fields: string[];
    provider_sourced_fields: string[];
    open_questions: string[];
    remote_review_ready: boolean;
    in_person_review_recommended: boolean;
  };
};

export type LeadDetail = LeadListItem & {
  land_acquisition_profile: LandAcquisitionProfile | null;
  property_intelligence: {
    research_status: string;
    research_profile: string;
    snapshot_id: string | null;
    version_number: number | null;
    snapshot_status: string | null;
    completeness_score: number;
    confidence_score: number;
    captured_at: string | null;
    expires_at: string | null;
    is_stale: boolean;
    facts: Record<string, { value?: unknown; source?: string; observed_at?: string; unit?: string }>;
    valuation: Record<string, unknown>;
    comparables: Array<Record<string, unknown>>;
    market_context: Record<string, unknown>;
    sources: Array<Record<string, unknown>>;
    conflicts: Array<Record<string, unknown>>;
    image_source: string;
    image_available: boolean;
    image_views: string[];
    image_url: string | null;
    image_attribution: string | null;
    imagery_date: string | null;
    last_error: string | null;
  };
  contact_methods: Array<{
    id: string;
    method_type: string;
    value: string;
    is_primary: boolean;
  }>;
  assignable_users: Array<{
    id: string;
    display_name: string;
    email: string;
  }>;
  consent_records: Array<{
    id: string;
    channel: string;
    status: string;
    source: string;
    wording_version: string;
    wording: string;
    normalized_address: string | null;
    captured_ip: string | null;
    created_at: string;
  }>;
  sms_eligibility: {
    can_send: boolean;
    recipient: string | null;
    consent_status: string;
    is_suppressed: boolean;
    provider_configured: boolean;
    within_allowed_hours: boolean;
    blockers: string[];
  };
  voice_eligibility: {
    can_call: boolean;
    recipient: string | null;
    consent_status: string;
    is_suppressed: boolean;
    provider_configured: boolean;
    within_allowed_hours: boolean;
    blockers: string[];
  };
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
    work_kind: string;
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
    comp_search_level: string | null;
    repair_catalog_version: string | null;
    comp_snapshot: Array<{
      key: string;
      address: string;
      grade: string | null;
      search_level: string | null;
      condition: string | null;
      adjusted_value_cents: number | null;
    }>;
    repair_snapshot: Array<{
      category: string;
      scope_status: string;
      expected_cents: number | null;
      confirmation_status: string | null;
    }>;
    adjustment_snapshot: {
      status: string;
      shadow_arv_point_cents: number | null;
      point_delta_cents: number | null;
      supported_count: number;
      withheld_count: number;
    } | null;
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

export type BuyerAssetFocus = "house" | "land" | "both";

export type BuyerBuyBoxAsset = "house" | "land";

export type BuyerBuyBoxGeography = {
  jurisdiction: "state" | "county" | "city" | "postal_code" | "radius";
  value: string;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  radius_miles: number | null;
};

export type BuyerPurchaseCapacity = {
  available_capital_cents: number | null;
  max_concurrent_purchases: number | null;
  target_purchases_per_month: number | null;
};

export type BuyerBuyBoxCriteriaBase = {
  asset_class: BuyerBuyBoxAsset;
  geographies: BuyerBuyBoxGeography[];
  excluded_geographies: BuyerBuyBoxGeography[];
  strategies: string[];
  exclusions: string[];
  min_price_cents: number | null;
  max_price_cents: number | null;
  funding_methods: string[];
  capacity: BuyerPurchaseCapacity;
};

export type HouseBuyerBuyBoxCriteria = BuyerBuyBoxCriteriaBase & {
  asset_class: "house";
  property_types: string[];
  rehab_tolerance: string[];
  occupancy_preferences: string[];
  min_bedrooms: number | null;
  max_bedrooms: number | null;
  min_bathrooms: number | null;
  max_bathrooms: number | null;
  min_living_area_sqft: number | null;
  max_living_area_sqft: number | null;
  min_year_built: number | null;
  max_year_built: number | null;
};

export type LandBuyerBuyBoxCriteria = BuyerBuyBoxCriteriaBase & {
  asset_class: "land";
  min_acres: number | null;
  max_acres: number | null;
  intended_uses: string[];
  zoning_codes: string[];
  access_preferences: string[];
  utility_preferences: string[];
  terrain_preferences: string[];
  flood_zone_tolerance: "avoid" | "review" | "accepted";
  wetlands_tolerance: "avoid" | "review" | "accepted";
};

export type BuyerBuyBoxCriteria = HouseBuyerBuyBoxCriteria | LandBuyerBuyBoxCriteria;

export type BuyerBuyBoxVersion = {
  id: string;
  buy_box_id: string;
  asset_class: BuyerBuyBoxAsset;
  version_number: number;
  is_current: boolean;
  verification_status: string;
  source: string;
  change_reason: string | null;
  criteria: BuyerBuyBoxCriteria;
  created_by_user_id: string | null;
  verified_by_user_id: string | null;
  verified_at: string | null;
  effective_at: string;
  superseded_at: string | null;
  created_at: string;
};

export type BuyerBuyBoxSummary = {
  buy_box_id: string;
  asset_class: BuyerBuyBoxAsset;
  current_version: number;
  verification_status: string;
  verified_at: string | null;
  updated_at: string;
  criteria: BuyerBuyBoxCriteria;
};

export type BuyerTimelineItem = {
  id: string;
  category: string;
  event_type: string;
  occurred_at: string;
  status: string | null;
  summary: string;
  body: string | null;
  direction: string | null;
  channel: string | null;
  disposition_case_id: string | null;
};

export type BuyerProofDocument = {
  id: string;
  buyer_id: string;
  status: string;
  institution_name: string | null;
  verified_amount_cents: number | null;
  expires_at: string | null;
  file_name: string;
  content_type: string;
  file_size: number;
  malware_scan_status: string;
  storage_provider: string;
  retention_until: string | null;
  verified_by_user_id: string | null;
  verified_at: string | null;
  verification_source: string | null;
  notes: string | null;
  content_url: string;
  created_at: string;
};

export type BuyerListItem = {
  id: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  normalized_email: string | null;
  normalized_phone: string | null;
  buyer_type: string;
  status: string;
  source_key: string;
  source_detail: string | null;
  source_external_key: string | null;
  created_by_user_id: string | null;
  created_by_name: string | null;
  created_by_email: string | null;
  relationship_owner_user_id: string | null;
  relationship_owner_name: string | null;
  relationship_status: string;
  tier: string;
  temperature: string;
  tags: string[];
  asset_focus: BuyerAssetFocus | null;
  last_contact_at: string | null;
  next_follow_up_at: string | null;
  verification_status: string;
  verified_by_user_id: string | null;
  verified_at: string | null;
  last_verified_at: string | null;
  archived_at: string | null;
  archived_by_user_id: string | null;
  archive_reason: string | null;
  proof_of_funds_status: string;
  max_purchase_price_cents: number | null;
  reliability_score_basis_points: number;
  completed_deals: number;
  failed_deals: number;
  proof_of_funds_expires_at: string | null;
  notes: string | null;
  phone_permission: BuyerPermissionEvidence;
  sms_permission: BuyerPermissionEvidence;
  permission_history: BuyerPermissionHistoryEntry[];
  criteria: {
    version_number: number;
    markets: string | null;
    property_types: string | null;
    min_price_cents: number | null;
    max_price_cents: number | null;
    rehab_levels: string | null;
    notes: string | null;
  } | null;
  buy_boxes: BuyerBuyBoxSummary[];
  created_at: string;
  updated_at: string;
};

export type BuyerProfile = {
  buyer: BuyerListItem;
  asset_focus: BuyerAssetFocus | null;
  legacy_criteria: {
    verification_status: "unverified";
    criteria: NonNullable<BuyerListItem["criteria"]>;
  } | null;
  criteria_versions: BuyerBuyBoxVersion[];
  timeline: {
    items: BuyerTimelineItem[];
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
};

export type BuyerPermissionEvidence = {
  status: string;
  source: string | null;
  recorded_at: string | null;
  normalized_address: string | null;
  wording_version: string | null;
};

export type BuyerPermissionHistoryEntry = BuyerPermissionEvidence & {
  channel: string;
};

export type BuyerRelationshipOwner = {
  user_id: string;
  display_name: string;
  email: string;
};

export type BuyerDuplicateMatch = {
  buyer_id: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  status: string;
  matched_fields: string[];
  reasons: string[];
};

export type BuyerDuplicatePreflight = {
  has_matches: boolean;
  normalized_email: string | null;
  normalized_phone: string | null;
  normalized_company_name: string | null;
  matches: BuyerDuplicateMatch[];
};

export type BuyerQuery = {
  assetClass?: BuyerAssetFocus | "";
  q?: string;
  page?: number;
  pageSize?: number;
  status?: string;
  ownerUserId?: string;
  sourceKey?: string;
};

export type BuyerPage = {
  buyers: BuyerListItem[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  relationshipOwners: BuyerRelationshipOwner[];
  sourceOptions: string[];
  apiConnected: boolean;
  errorMessage: string | null;
};

export type BuyerDataProvider = {
  provider: string;
  configured: boolean;
  live_search_enabled: boolean;
  message: string;
  connected: boolean | null;
  plan_name: string | null;
  is_paid: boolean | null;
  billing_cycle_end: string | null;
  credits_remaining: number | null;
  credits_used: number | null;
  credits_total: number | null;
};

export type BuyerDiscoveryEstimate = {
  disposition_case_id: string;
  requested_candidates: number;
  provider_result_limit: number;
  total_matching_properties: number;
  estimated_credits: number;
  estimated_property_credits: number;
  estimated_people_credits: number;
  credits_remaining: number;
  enough_credits: boolean;
  message: string;
};

export type BuyerDiscoveryCandidate = {
  id: string;
  buyer_id: string | null;
  provider: string;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  market: string;
  state: string;
  property_types: string[];
  observed_purchase_count: number;
  no_mortgage_count: number;
  last_purchase_date: string | null;
  min_purchase_price_cents: number | null;
  max_purchase_price_cents: number | null;
  score_basis_points: number;
  score_components: Record<string, number>;
  evidence_snapshot: Record<string, unknown>;
  status: string;
};

export type BuyerDiscoveryRun = {
  id: string;
  disposition_case_id: string;
  provider: string;
  status: string;
  search_snapshot: Record<string, unknown>;
  result_count: number;
  imported_count: number;
  credit_summary: Record<string, unknown> | null;
  error_message: string | null;
  completed_at: string | null;
  candidates: BuyerDiscoveryCandidate[];
  created_at: string;
};

export type DispositionBuyerPoolSource = "all" | "mine" | "network" | "external";

export type DispositionBuyerPoolStage =
  | "all"
  | "discovered"
  | "needs_review"
  | "eligible"
  | "shortlisted"
  | "contacted"
  | "interested"
  | "showing"
  | "offer"
  | "pass"
  | "selected"
  | "backup"
  | "fallout";

export type DispositionBuyerPoolRun = {
  id: string;
  version_number: number;
  matcher_version: string;
  score_policy_version: string;
  generated_at: string;
};

export type DispositionBuyerPoolEntry = {
  id: string;
  candidate_id: string;
  buyer_id: string | null;
  discovery_candidate_id: string | null;
  source_type: Exclude<DispositionBuyerPoolSource, "all">;
  origin_type: string;
  provider: string | null;
  external_key: string | null;
  name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  decision_status: string;
  lifecycle_stage: string;
  decision_reason: string | null;
  lock_version: number;
  overlap_status: string;
  possible_buyer_id: string | null;
  possible_buyer_name: string | null;
  possible_buyer_company_name: string | null;
  overlap_evidence: Record<string, unknown>;
  score_basis_points: number;
  rank: number | null;
  eligibility_status: string;
  score_components: Record<string, number>;
  score_explanation: string[];
  supporting_evidence: Record<string, unknown>[];
  conflicting_evidence: Record<string, unknown>[];
  disqualifying_reasons: string[];
  buy_box_version_id: string | null;
  proof_status: string;
  proof_expires_at: string | null;
  relationship_status: string | null;
  tier: string | null;
  temperature: string | null;
};

export type DispositionBuyerPoolPage = {
  case_id: string;
  run: DispositionBuyerPoolRun | null;
  total: number;
  page: number;
  page_size: number;
  entries: DispositionBuyerPoolEntry[];
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

export type DispositionOfferRiskFlag = {
  code: string;
  severity: "info" | "warning" | "danger";
  message: string;
  evidence: Record<string, unknown>;
};

export type DispositionOfferRoomOffer = {
  id: string;
  buyer_id: string;
  buyer_name: string;
  amount_cents: number;
  earnest_money_cents: number | null;
  deposit_due_at: string | null;
  due_diligence_days: number | null;
  contingencies: string[];
  contingencies_confirmed: boolean;
  proposed_closing_at: string | null;
  funding_method: string;
  funding_confidence_basis_points: number;
  proof_document_id: string | null;
  proof_status: string;
  proof_verified_amount_cents: number | null;
  proof_expires_at: string | null;
  special_terms: string | null;
  notes: string | null;
  status: string;
  lock_version: number;
  received_at: string;
  updated_at: string;
  risk_score_basis_points: number;
  risk_flags: DispositionOfferRiskFlag[];
  strengths: string[];
  execution_score_basis_points: number;
  reliability_score_basis_points: number;
  reliability_evidence: string[];
  comparison_rank: number;
  is_recommended: boolean;
};

export type DispositionOfferSelectionSlot = {
  role: "primary" | "backup";
  rank: number;
  offer_id: string;
  buyer_id: string;
  buyer_name: string;
  amount_cents: number;
  offer_snapshot: Record<string, unknown>;
  readiness_status: "ready" | "provisional";
  readiness_blockers: string[];
};

export type DispositionOfferSelection = {
  id: string;
  status: string;
  lock_version: number;
  primary: DispositionOfferSelectionSlot | null;
  backups: DispositionOfferSelectionSlot[];
  reason: string;
  evidence_hash: string;
  approved_by_user_id: string;
  approved_at: string;
  replaced_at: string | null;
};

export type DispositionOfferNegotiationEvent = {
  id: string;
  offer_id: string;
  buyer_id: string;
  buyer_name: string;
  event_type: string;
  direction: string;
  summary: string;
  metadata: Record<string, unknown>;
  occurred_at: string;
  actor_user_id: string;
};

export type DispositionDeadlineAlert = {
  id: string;
  checkpoint_id: string;
  status: string;
  severity: string;
  title: string;
  message: string;
  due_at: string;
  deadline_version: number;
  acknowledged_by_user_id: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
};

export type DispositionClosingCheckpoint = {
  id: string;
  selection_id: string | null;
  checkpoint_type: string;
  label: string;
  canonical_source: string;
  source_record_id: string | null;
  due_at: string;
  status: string;
  lock_version: number;
  deadline_version: number;
  offer_id: string | null;
  buyer_id: string | null;
  buyer_name: string | null;
  responsible_user_id: string | null;
  completed_at: string | null;
  notes: string | null;
  evidence: Record<string, unknown>;
  is_overdue: boolean;
  active_alert: DispositionDeadlineAlert | null;
};

export type DispositionReplacementOption = {
  offer_id: string;
  buyer_id: string;
  buyer_name: string;
  backup_rank: number | null;
  comparison_rank: number;
  amount_cents: number;
  execution_score_basis_points: number;
  risk_score_basis_points: number;
  eligible: boolean;
  blockers: string[];
};

export type DispositionOfferOutcome = {
  id: string;
  selection_id: string | null;
  offer_id: string;
  buyer_id: string;
  buyer_name: string;
  outcome_type: string;
  cause_category: string;
  reason: string;
  details: string | null;
  evidence: Record<string, unknown>;
  occurred_at: string;
  completed_delta: number;
  failed_delta: number;
  reliability_delta_basis_points: number;
};

export type DispositionOfferRoomWorkspace = {
  case_id: string;
  case_status: string;
  currency: string;
  generated_at: string;
  offers: DispositionOfferRoomOffer[];
  current_selection: DispositionOfferSelection | null;
  selection_history: DispositionOfferSelection[];
  negotiation_history: DispositionOfferNegotiationEvent[];
  checkpoints: DispositionClosingCheckpoint[];
  alerts: DispositionDeadlineAlert[];
  replacement_options: DispositionReplacementOption[];
  outcomes: DispositionOfferOutcome[];
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
  minimum_acceptable_cents: number | null;
  desired_assignment_fee_cents: number | null;
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
  can_view_private_economics: boolean;
  metrics: { active_cases: number; packages_pending: number; buyer_selected: number; reconciliation_pending: number; below_margin_target: number };
  eligible_transactions: Array<{ id: string; seller_name: string; property_address: string; purchase_price_cents: number | null; assignment_fee_cents: number | null }>;
  cases: DispositionCase[];
};

export type DispositionPackageEvidenceClassification =
  | "verified_fact"
  | "seller_statement"
  | "provider_signal"
  | "stonegate_analysis"
  | "unknown";

export type DispositionPackageEvidence = {
  key: string;
  label: string;
  classification: DispositionPackageEvidenceClassification;
  value: unknown;
  provenance: Record<string, unknown>;
  captured_at: string | null;
  expires_at: string | null;
  freshness: "current" | "stale" | "unknown";
};

export type DispositionPackageReadinessCheck = {
  key: string;
  label: string;
  status: "ready" | "warning" | "blocked";
  detail: string;
  source_label: string | null;
  captured_at: string | null;
  remediation: { label: string; href: string } | null;
};

export type DispositionPackageReadiness = {
  status: "ready" | "warnings" | "blocked" | "stale";
  blockers: string[];
  warnings: string[];
  unknowns: string[];
  checks: DispositionPackageReadinessCheck[];
  ready_count: number;
  warning_count: number;
  blocked_count: number;
  unknown_count: number;
};

export type DispositionPackagePublicSnapshot = Record<string, unknown> & {
  property_address?: string;
  property_type?: string | null;
  asking_price_cents?: number | null;
  headline?: string;
  description?: string;
  highlights?: string[];
  unknowns?: string[];
  disclaimer?: string;
};

export type DispositionPackageInternalEconomics = Record<string, unknown> & {
  contract_purchase_price_cents?: number | null;
  buyer_asking_price_cents?: number | null;
  minimum_acceptable_cents?: number | null;
  desired_assignment_fee_cents?: number | null;
  gross_spread_at_ask_cents?: number | null;
  approval_authority?: string | null;
};

export type DispositionPackageVersion = {
  id: string;
  disposition_case_id: string;
  version_number: number;
  lock_version: number;
  status: "draft" | "approved" | "superseded" | "rejected";
  policy_version: string;
  renderer_version: string;
  public_snapshot: DispositionPackagePublicSnapshot;
  private_economics_snapshot: DispositionPackageInternalEconomics | null;
  evidence_manifest: DispositionPackageEvidence[];
  readiness: DispositionPackageReadiness;
  source_fingerprint: string;
  email_summary: string;
  sms_summary: string;
  pdf_file_name: string | null;
  pdf_size: number | null;
  pdf_sha256: string | null;
  created_by_user_id: string;
  approved_by_user_id: string | null;
  approval_reason: string | null;
  approved_at: string | null;
  created_at: string;
  is_current: boolean;
};

export type DispositionPackageWorkspace = {
  case_id: string;
  can_approve: boolean;
  can_view_internal_economics: boolean;
  current_source_fingerprint: string;
  current_readiness: DispositionPackageReadiness;
  public_preview: DispositionPackagePublicSnapshot;
  private_economics: DispositionPackageInternalEconomics | null;
  evidence_manifest: DispositionPackageEvidence[];
  email_summary: string;
  sms_summary: string;
  latest_version: DispositionPackageVersion | null;
  approved_version: DispositionPackageVersion | null;
  approved_package_is_current: boolean;
  versions: DispositionPackageVersion[];
};

export type DispositionProviderPermission = {
  can_prepare: boolean;
  can_approve: boolean;
  can_record_manual: boolean;
  can_disconnect: boolean;
  can_export: boolean;
};

export type DispositionProviderVerificationGate = {
  provider_key: "investorlift";
  mode: "manual";
  api_contract_verified: boolean;
  live_transport_enabled: boolean;
  credential_required: boolean;
  house_only: boolean;
  blockers: string[];
  supported_manual_capabilities: string[];
  unverified_capabilities: string[];
};

export type DispositionProviderAccount = {
  id: string;
  provider_key: "investorlift";
  provider_label: string;
  mode: "manual";
  status: "manual_ready";
  capability_snapshot: Record<string, unknown>;
  connected_at: string;
};

export type DispositionProviderApprovedPackage = {
  package_version_id: string;
  version_number: number;
  source_fingerprint: string;
  approved_at: string;
  is_current: boolean;
};

export type DispositionProviderManualStatus =
  | "draft"
  | "active"
  | "paused"
  | "under_contract"
  | "sold"
  | "archived"
  | "unknown";

export type DispositionProviderListing = {
  id: string;
  provider_account_id: string;
  disposition_case_id: string;
  status: "draft" | "release_approved" | "manual_published" | "disconnected";
  lock_version: number;
  package_version_id: string | null;
  latest_revision_id: string | null;
  approved_revision_id: string | null;
  external_property_id: string | null;
  external_url: string | null;
  provider_status: DispositionProviderManualStatus | null;
  public_payload_sha256: string | null;
  package_source_fingerprint: string | null;
  manual_published_at: string | null;
  last_refreshed_at: string | null;
  disconnected_at: string | null;
  disconnect_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type DispositionProviderListingRevision = {
  id: string;
  listing_id: string;
  package_version_id: string;
  revision_number: number;
  lock_version: number;
  status: "draft" | "approved" | "superseded";
  public_payload: Record<string, unknown>;
  public_payload_sha256: string;
  package_source_fingerprint: string;
  created_by_user_id: string;
  approved_by_user_id: string | null;
  approval_reason: string | null;
  approved_at: string | null;
  created_at: string;
  is_current: boolean;
};

export type DispositionProviderSourceLink = {
  id: string;
  listing_id: string;
  listing_revision_id: string;
  external_property_id: string;
  external_url: string;
  provider_status: DispositionProviderManualStatus;
  source_snapshot_sha256: string;
  observed_at: string;
  note: string | null;
  created_by_user_id: string;
  created_at: string;
};

export type DispositionProviderEvidence = {
  id: string;
  listing_id: string;
  event_type: "inquiry" | "offer" | "engagement";
  external_event_id: string | null;
  review_status: "staged" | "reviewed" | "dismissed";
  lock_version: number;
  occurred_at: string;
  buyer_name: string | null;
  buyer_email: string | null;
  buyer_phone: string | null;
  offer_amount_cents: number | null;
  message: string | null;
  metadata: Record<string, unknown>;
  evidence_sha256: string;
  review_note: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  selection_eligible: false;
};

export type DispositionProviderSyncRun = {
  id: string;
  listing_id: string | null;
  operation: string;
  status: "completed" | "failed";
  mode: "manual";
  request_sha256: string;
  result_summary: Record<string, unknown>;
  error_message: string | null;
  started_at: string;
  completed_at: string;
};

export type DispositionProviderWorkspace = {
  case_id: string;
  provider_key: "investorlift";
  provider_label: string;
  house_only: boolean;
  eligible: boolean;
  eligibility_blockers: string[];
  permissions: DispositionProviderPermission;
  verification_gate: DispositionProviderVerificationGate;
  account: DispositionProviderAccount | null;
  approved_package: DispositionProviderApprovedPackage | null;
  listing: DispositionProviderListing | null;
  revisions: DispositionProviderListingRevision[];
  source_links: DispositionProviderSourceLink[];
  staged_events: DispositionProviderEvidence[];
  recent_runs: DispositionProviderSyncRun[];
  warnings: string[];
};

export type DispositionOutreachChannel = "email" | "sms";

export type DispositionOutreachRevisionStatus =
  | "draft"
  | "review_required"
  | "approved"
  | "queued"
  | "sending"
  | "paused"
  | "provider_degraded"
  | "completed"
  | "completed_with_failures"
  | "cancelled"
  | "invalidated";

export type DispositionOutreachSender = {
  id: string;
  channel: DispositionOutreachChannel;
  label: string;
  address: string;
  is_default: boolean;
};

export type DispositionOutreachPreparedRecipient = {
  id: string;
  buyer_id: string;
  buyer_name: string;
  company_name: string | null;
  available_channels: DispositionOutreachChannel[];
  captured_email: string | null;
  captured_phone: string | null;
};

export type DispositionOutreachDelivery = {
  id: string;
  campaign_recipient_id: string;
  buyer_id: string;
  buyer_name: string;
  company_name: string | null;
  channel: DispositionOutreachChannel;
  destination: string;
  conversation_id: string | null;
  subject: string | null;
  body: string;
  body_hash: string;
  eligibility_status: "eligible" | "ineligible";
  eligibility_snapshot: Record<string, unknown>;
  exclusion_reason: string | null;
  status: string;
  attempt_count: number;
  provider: string | null;
  provider_message_id: string | null;
  created_at: string;
};

export type DispositionOutreachRevision = {
  id: string;
  campaign_id: string;
  case_id: string;
  package_version_id: string;
  revision_number: number;
  lock_version: number;
  status: DispositionOutreachRevisionStatus;
  mode: "supervised";
  recipient_cap: number;
  recipient_manifest_hash: string;
  approval_hash: string | null;
  package_source_fingerprint: string;
  artifact_sha256: string;
  sender_snapshot: Record<string, unknown>;
  created_by_user_id: string;
  approved_by_user_id: string | null;
  approval_reason: string | null;
  approved_at: string | null;
  queued_at: string | null;
  paused_at: string | null;
  cancelled_at: string | null;
  completed_at: string | null;
  delivery_counts: Record<string, number>;
  deliveries: DispositionOutreachDelivery[];
  created_at: string;
};

export type DispositionOutreachWorkspace = {
  case_id: string;
  campaign_id: string | null;
  package_version_id: string | null;
  package_source_fingerprint: string | null;
  artifact_sha256: string | null;
  hard_recipient_cap: number;
  readiness_status: "ready" | "blocked";
  blockers: string[];
  prepared_recipients: DispositionOutreachPreparedRecipient[];
  available_senders: DispositionOutreachSender[];
  latest_revision: DispositionOutreachRevision | null;
  revisions: DispositionOutreachRevision[];
};

export type DispositionDeskScope = "mine" | "team";

export type DispositionDeskCategory =
  | "today"
  | "active_deals"
  | "buyer_follow_ups"
  | "replies"
  | "offers"
  | "deadlines";

export type DispositionDeskSectionKey =
  | DispositionDeskCategory
  | "coverage_warnings"
  | "deal_records";

export type DispositionDeskSectionState = {
  total: number;
  returned: number;
  has_more: boolean;
  offset: number;
};

export type DispositionDeskAction = {
  label: string;
  href: string;
};

export type DispositionDeskItem = {
  key: string;
  category: DispositionDeskCategory;
  title: string;
  context: string;
  owner_user_id: string | null;
  owner_name: string;
  due_at: string | null;
  reason: string;
  blocker: string | null;
  severity: "info" | "warning" | "danger";
  deal_id: string | null;
  buyer_id: string | null;
  conversation_id: string | null;
  task_id: string | null;
  offer_id: string | null;
  disposition_case_id: string | null;
  primary_action: DispositionDeskAction;
  secondary_action: DispositionDeskAction | null;
};

export type DispositionDeskOverview = {
  requested_scope: DispositionDeskScope;
  effective_scope: DispositionDeskScope;
  scope_label: string;
  scope_member_count: number;
  can_view_team: boolean;
  scope_notice: string | null;
  can_edit_buyers: boolean;
  metrics: {
    today: number;
    active_deals: number;
    buyer_follow_ups: number;
    replies: number;
    offers: number;
    deadlines: number;
    weak_coverage: number;
  };
  buyer_network: {
    total: number;
    active: number;
    needs_review: number;
    unassigned: number;
    missing_proof: number;
    expiring_proof: number;
    missing_criteria: number;
  };
  today: DispositionDeskItem[];
  active_deals: DispositionDeskItem[];
  buyer_follow_ups: DispositionDeskItem[];
  replies: DispositionDeskItem[];
  offers: DispositionDeskItem[];
  deadlines: DispositionDeskItem[];
  coverage_warnings: DispositionDeskItem[];
  deal_records: DealQueueItem[];
  sections: Record<DispositionDeskSectionKey, DispositionDeskSectionState>;
  source_health: {
    generated_at: string;
    canonical_data_status: "current";
    external_provider_status: "not_configured" | "configured_unverified" | "available" | "unavailable";
    message: string;
  };
};

export type DispositionIntelligenceState =
  | "known"
  | "partial"
  | "unavailable";

export type DispositionIntelligenceDataState = DispositionIntelligenceState;

export type DispositionIntelligenceQuery = {
  deal_id?: string;
  buyer_id?: string;
  agent_user_id?: string;
  source?: string;
  market?: string;
  asset_class?: string;
  start_at?: string;
  end_at?: string;
};

export type DispositionIntelligenceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type DispositionIntelligenceQualitySignal = {
  key: string;
  label: string;
  state: DispositionIntelligenceState;
  detail: string;
  record_count: number;
};

export type DispositionIntelligenceMilestone = {
  key: string;
  label: string;
  state: DispositionIntelligenceState;
  count: number;
  median_hours: number | null;
  p90_hours: number | null;
};

export type DispositionIntelligenceRate = {
  key: string;
  label: string;
  state: DispositionIntelligenceState;
  numerator: number;
  denominator: number;
  rate_percent: number | null;
};

export type DispositionIntelligenceSourceRow = {
  key: string;
  label: string;
  category: string;
  state: DispositionIntelligenceState;
  activity_count: number;
  offers: number;
  selected_buyers: number;
  completed_assignments: number;
  collected_revenue_cents: number | null;
};

export type DispositionIntelligenceBuyerRow = {
  buyer_id: string;
  name: string;
  state: DispositionIntelligenceState;
  replies: number;
  showings: number;
  offers: number;
  selections: number;
  completed_assignments: number;
  fallouts: number;
  retrades: number;
  reliability_score_basis_points: number | null;
  provenance: string;
};

export type DispositionIntelligenceAgentRow = {
  user_id: string;
  name: string;
  state: DispositionIntelligenceState;
  role: string;
  packages_approved: number;
  outreach_sent: number;
  replies_reviewed: number;
  selections_approved: number;
  outcomes_recorded: number;
  completed_assignments: number;
};

export type DispositionIntelligenceProvenance = {
  metric_key: string;
  state: DispositionIntelligenceState;
  canonical_sources: string[];
  definition: string;
};

export type DispositionIntelligenceResponse = {
  generated_at: string;
  scope: {
    start_at: string | null;
    end_at: string | null;
    filters_applied: {
      deal_id: string | null;
      buyer_id: string | null;
      agent_user_id: string | null;
      source: string | null;
      market: string | null;
      asset_class: string | null;
      start_at: string | null;
      end_at: string | null;
    };
  };
  access: {
    private_economics_visible: boolean;
  };
  data_state: DispositionIntelligenceDataState;
  data_quality: DispositionIntelligenceQualitySignal[];
  activity: {
    cases: number;
    packages_approved: number;
    outreach_sent: number;
    replies: number;
    inquiries: number;
    showings: number;
    offers: number;
    selected_buyers: number;
    deposits: number;
  };
  economics: {
    state: DispositionIntelligenceState;
    completed_assignments: number;
    reconciled_completed_assignments: number;
    contracted_assignment_spread_cents: number | null;
    collected_revenue_cents: number | null;
    approved_company_profit_cents: number | null;
    campaign_cost_cents: number | null;
    cost_per_offer_cents: number | null;
    cost_per_selected_buyer_cents: number | null;
    cost_per_completed_assignment_cents: number | null;
    detail: string;
  };
  milestones: DispositionIntelligenceMilestone[];
  rates: DispositionIntelligenceRate[];
  sources: DispositionIntelligenceSourceRow[];
  buyers: DispositionIntelligenceBuyerRow[];
  agents: DispositionIntelligenceAgentRow[];
  learning: {
    state: DispositionIntelligenceState;
    human_led_count: number;
    ai_assisted_count: number;
    minimum_comparison_sample: number;
    comparison_allowed: boolean;
    notice: string;
    corrections: {
      package_revisions: number;
      match_overrides: number;
      ai_corrections: number;
      backup_buyer_saves: number;
    };
  };
  provenance: DispositionIntelligenceProvenance[];
  filter_options: {
    deals: DispositionIntelligenceFilterOption[];
    buyers: DispositionIntelligenceFilterOption[];
    agents: DispositionIntelligenceFilterOption[];
    sources: DispositionIntelligenceFilterOption[];
    markets: DispositionIntelligenceFilterOption[];
    asset_classes: DispositionIntelligenceFilterOption[];
  };
};

export type DispositionCopilotCitation = {
  citation_id: string;
  source_type: "case_snapshot" | "package_version" | "buyer_pool_entry" |
    "buyer_match" | "buyer_contact_status" | "buyer_proof" | "buyer_offer" |
    "offer_revision" | "buyer_engagement" | "outreach_reply" |
    "provider_evidence";
  source_id: string;
  label: string;
  fact: string;
  status: string;
  observed_at: string | null;
};

export type DispositionCopilotQualityEvaluation = {
  scenario_group: "normal" | "incomplete" | "conflicting" | "policy_blocked" |
    "stale" | "adversarial";
  critical_authority_violation: boolean;
  unsupported_or_hallucinated_citation: boolean;
  package_fact_correctness: "correct" | "partially_correct" | "incorrect" |
    "not_applicable";
  buyer_match_relevance: "relevant" | "partially_relevant" | "not_relevant" |
    "not_applicable";
  reply_classification_accuracy: "correct" | "partially_correct" | "incorrect" |
    "not_applicable";
  next_action_usefulness: "useful" | "correctable" | "not_useful" |
    "not_applicable";
  notes: string | null;
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
      citation_ids: string[];
    }>;
    offer_comparison: Array<{
      offer_id: string;
      buyer_id: string | null;
      buyer_name: string;
      strength: "strong" | "acceptable" | "weak" | "ineligible";
      rationale: string[];
      risks: string[];
      execution_risk: "low" | "moderate" | "high" | "unknown";
      citation_ids: string[];
    }>;
    buyer_outreach_subject: string;
    buyer_outreach_body: string;
    recommended_internal_actions: string[];
    relationship_update_proposals: string[];
    risk_alerts: string[];
    uncertainties: string[];
    evidence: string[];
    drafts: Array<{
      draft_type: "package_summary" | "recipient_segment" | "email" | "sms" |
        "call_brief" | "follow_up";
      buyer_id: string | null;
      title: string;
      body: string;
      citation_ids: string[];
      requires_human_approval: true;
    }>;
    reply_classifications: Array<{
      source_type: "outreach_reply" | "provider_evidence";
      source_id: string;
      classification: "interested" | "inquiry" | "pass" | "offer_intent" |
        "offer" | "opt_out" | "wrong_person" | "needs_review";
      confidence: number;
      rationale: string;
      citation_ids: string[];
      requires_human_review: true;
    }>;
    next_actions: Array<{
      action_type: "call" | "proof_request" | "showing" | "counter" |
        "deadline_action" | "backup_activation" | "follow_up" |
        "package_correction" | "reply_review";
      buyer_id: string | null;
      offer_id: string | null;
      action: string;
      rationale: string;
      priority: "low" | "normal" | "high" | "urgent";
      confidence: number;
      citation_ids: string[];
      requires_human_approval: true;
    }>;
    buyer_update_proposals: Array<{
      buyer_id: string;
      field_name: "relationship_status" | "tier" | "temperature" |
        "preferred_markets" | "preferred_property_types" |
        "proof_of_funds_status" | "reliability_note";
      proposed_value: string;
      rationale: string;
      confidence: number;
      citation_ids: string[];
      requires_human_approval: true;
    }>;
    can_send_outreach: false;
    can_select_buyer: false;
    can_bind_stonegate: false;
    can_update_buyer: false;
    confidence: number;
  };
  evidence_fingerprint: string;
  evidence_citations: DispositionCopilotCitation[];
  evidence_status: "current" | "stale" | "unknown";
  stale_reason: string | null;
  permitted_review_decisions: Array<"accepted" | "edited" | "rejected" | "ignored">;
  ai_trace: {
    model_name: string;
    prompt_version_id: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    cost_microusd: number | null;
    latency_ms: number | null;
    started_at: string;
    completed_at: string | null;
  } | null;
  authority: {
    can_send_outreach: false;
    can_select_buyer: false;
    can_bind_stonegate: false;
    can_update_buyer: false;
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
    accepted: number;
    corrected: number;
    rejected: number;
    ignored: number;
    accepted_or_corrected_rate_basis_points: number;
    correction_rate_basis_points: number;
    rejection_rate_basis_points: number;
    ignore_rate_basis_points: number;
    estimated_time_saved_minutes: number;
    average_latency_ms: number | null;
    p95_latency_ms: number | null;
    average_input_tokens: number | null;
    average_output_tokens: number | null;
    average_cost_microusd: number | null;
    total_cost_microusd: number;
    pilot_evaluation: {
      minimum_evaluated_recommendations: number;
      minimum_distinct_cases: number;
      minimum_domain_sample_size: number;
      evaluated_recommendations: number;
      distinct_cases: number;
      critical_authority_violations: number;
      unsupported_or_hallucinated_citations: number;
      package_fact_correctness_basis_points: number;
      package_fact_sample_size: number;
      buyer_match_relevance_basis_points: number;
      buyer_match_sample_size: number;
      reply_classification_accuracy_basis_points: number;
      reply_classification_sample_size: number;
      next_action_useful_or_correctable_basis_points: number;
      next_action_sample_size: number;
      accept_or_correct_basis_points: number;
      trace_attribution_basis_points: number;
      pilot_ready: boolean;
      observed_scenario_groups: Array<
        "normal" | "incomplete" | "conflicting" | "policy_blocked" | "stale" |
        "adversarial"
      >;
      missing_scenario_groups: Array<
        "normal" | "incomplete" | "conflicting" | "policy_blocked" | "stale" |
        "adversarial"
      >;
      blockers: string[];
    };
  };
};

export type ManagementCopilotOutput = {
  brief: string;
  confirmed_facts: Array<{
    label: string;
    value: string;
    evidence: string[];
  }>;
  exceptions: Array<{
    severity: "info" | "warning" | "critical";
    category: string;
    title: string;
    detail: string;
    evidence: string[];
  }>;
  analysis: Array<{
    category: string;
    subject: string;
    signal: "positive" | "neutral" | "warning" | "critical";
    analysis: string;
    evidence: string[];
  }>;
  draft_actions: Array<{
    action: string;
    reason: string;
    owner: string;
    workspace: "dashboard" | "finance" | "marketing" | "operations" |
      "dispositions" | "transactions" | "ai";
    evidence: string[];
    requires_human_decision: true;
  }>;
  decision_requests: Array<{
    decision: string;
    why_now: string;
    options: string[];
    evidence: string[];
  }>;
  uncertainties: string[];
  evidence: string[];
  confidence: number;
};

export type ManagementCopilotRecommendation = {
  id: string;
  capability_key: "finance.reconcile" | "finance.tax_review" |
    "marketing.analyze" | "operations.brief";
  reporting_period_days: number;
  ai_run_log_id: string | null;
  status: string;
  output_payload: ManagementCopilotOutput;
  confidence_score: number | null;
  generated_at: string;
  reviewed_at: string | null;
};

export type ManagementCopilotOverview = {
  capability_key: "finance.reconcile" | "finance.tax_review" | "marketing.analyze" | "operations.brief";
  copilot_name: string;
  pilot_mode: "draft_only";
  runtime_status: string;
  capability_status: string;
  external_actions_blocked: boolean;
  reporting_period_days: number;
  health_score: number;
  health_band: "healthy" | "needs_review" | "critical";
  readiness_gaps: string[];
  risk_alerts: Array<{
    severity: "info" | "warning" | "critical";
    item: string;
    reason: string;
    evidence: string[];
  }>;
  metric_cards: Array<{
    label: string;
    value: string;
    detail: string;
    tone: "neutral" | "info" | "success" | "warning" | "danger";
  }>;
  recommendations: ManagementCopilotRecommendation[];
  metrics: {
    generated: number;
    reviewed: number;
    accepted_or_corrected_rate_basis_points: number;
    correction_rate_basis_points: number;
    rejection_rate_basis_points: number;
    blocked_output_count: number;
    average_latency_ms: number | null;
    total_cost_microusd: number;
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

export type AccountingSetup = {
  profile: {
    id: string;
    legal_entity_name: string;
    entity_type: string;
    federal_tax_classification: string;
    accounting_method: string;
    tax_year_end_month: number;
    tax_year_end_day: number;
    books_start_date: string | null;
    home_state: string;
    currency: string;
    owner_compensation_treatment: string;
    status: string;
    policy_version: number;
    tax_rule_year: number;
    notes: string | null;
    updated_at: string;
  };
  accounts: Array<{
    id: string;
    policy_version: number;
    code: string;
    system_key: string;
    name: string;
    account_type: string;
    subtype: string;
    normal_balance: string;
    tax_category: string;
    deal_tracking: boolean;
    is_active: boolean;
    description: string;
  }>;
  readiness_score: number;
  readiness_gaps: string[];
  policy_notes: string[];
  tax_copilot: {
    capability_key: string;
    mode: string;
    status: string;
    readiness_score: number;
    readiness_gaps: string[];
    review_scope: string[];
    prohibited_actions: string[];
    source_records: number;
    records_missing_notes: number;
  };
};

export type AccountingLedger = {
  summary: {
    draft_entries: number;
    approved_entries: number;
    posted_entries: number;
    reversed_entries: number;
    posted_amount_cents: number;
    out_of_balance_entries: number;
  };
  periods: Array<{
    id: string;
    period_key: string;
    period_start_at: string;
    period_end_at: string;
    status: string;
    review_started_at: string | null;
    closed_at: string | null;
    locked_at: string | null;
    reopened_at: string | null;
    reopen_reason: string | null;
    draft_entries: number;
    approved_entries: number;
    posted_entries: number;
  }>;
  entries: Array<{
    id: string;
    accounting_period_id: string;
    entry_number: string;
    entry_date: string;
    status: string;
    memo: string;
    source_type: string;
    source_id: string | null;
    posting_rule_version: number;
    evidence_references: string[];
    idempotency_key: string;
    currency: string;
    total_debits_cents: number;
    total_credits_cents: number;
    prepared_by_user_id: string;
    approved_by_user_id: string | null;
    posted_by_user_id: string | null;
    reversed_by_user_id: string | null;
    reverses_entry_id: string | null;
    reversal_entry_id: string | null;
    approved_at: string | null;
    posted_at: string | null;
    reversed_at: string | null;
    review_notes: string | null;
    created_at: string;
    lines: Array<{
      id: string;
      accounting_account_id: string;
      account_code: string;
      account_name: string;
      line_number: number;
      debit_cents: number;
      credit_cents: number;
      memo: string | null;
      deal_id: string | null;
      transaction_id: string | null;
    }>;
  }>;
};

export type AccountingOperations = {
  rules: Array<{
    id: string;
    rule_key: string;
    version_number: number;
    name: string;
    source_type: string;
    trigger_status: string;
    strategy_key: string;
    debit_account_key: string;
    credit_account_key: string;
    evidence_required: boolean;
    status: string;
    description: string;
    approved_by_user_id: string | null;
    approved_at: string | null;
    effective_at: string | null;
  }>;
  source_items: Array<{
    source_type: string;
    source_id: string;
    posting_purpose: string;
    label: string;
    amount_cents: number;
    occurred_at: string;
    status: string;
    readiness: string;
    readiness_detail: string;
    rule_id: string | null;
    rule_key: string;
    journal_entry_id: string | null;
    journal_status: string | null;
    evidence_references: string[];
    lead_id: string | null;
    deal_id: string | null;
    transaction_id: string | null;
  }>;
  obligations: Array<{
    id: string;
    obligation_type: string;
    direction: string;
    counterparty_name: string;
    user_id: string | null;
    expense_account_key: string | null;
    amount_cents: number;
    status: string;
    source_type: string | null;
    source_id: string | null;
    due_at: string | null;
    approved_by_user_id: string | null;
    approved_at: string | null;
    paid_at: string | null;
    payment_reference: string | null;
    evidence_references: string[];
    notes: string | null;
    created_at: string;
  }>;
  draft_rule_count: number;
  ready_item_count: number;
  exception_count: number;
};

export type VendorAccounting = {
  summary: {
    active_vendors: number;
    contractors: number;
    w9_action_required: number;
    draft_bills: number;
    open_payables: number;
    overdue_bills: number;
    open_payable_cents: number;
    paid_year_to_date_cents: number;
    private_documents: number;
  };
  vendors: Array<{
    id: string;
    counterparty_id: string;
    vendor_type: string;
    status: string;
    name: string;
    company_name: string | null;
    email: string | null;
    phone: string | null;
    default_expense_account_key: string | null;
    payment_terms_days: number;
    tax_reportable: boolean;
    w9_status: string;
    w9_requested_at: string | null;
    w9_received_at: string | null;
    w9_verified_at: string | null;
    remittance_address: string | null;
    notes: string | null;
    paid_year_to_date_cents: number;
    open_bill_count: number;
    document_count: number;
    created_at: string;
  }>;
  bills: Array<{
    id: string;
    vendor_profile_id: string;
    vendor_name: string;
    financial_obligation_id: string | null;
    bill_number: string;
    status: string;
    issue_at: string;
    due_at: string | null;
    amount_cents: number;
    currency: string;
    description: string;
    approved_at: string | null;
    paid_at: string | null;
    payment_reference: string | null;
    notes: string | null;
    evidence_count: number;
    evidence_references: string[];
    lines: Array<{
      id: string;
      line_number: number;
      description: string;
      amount_cents: number;
      expense_account_key: string;
      deal_id: string | null;
      transaction_id: string | null;
    }>;
    created_at: string;
  }>;
  documents: Array<{
    id: string;
    vendor_profile_id: string | null;
    vendor_bill_id: string | null;
    financial_obligation_id: string | null;
    transaction_id: string | null;
    document_type: string;
    title: string;
    status: string;
    is_sensitive: boolean;
    file_name: string;
    content_type: string;
    file_size: number;
    storage_provider: string;
    malware_scan_status: string;
    retention_until: string | null;
    occurred_at: string;
    notes: string | null;
    content_path: string;
  }>;
};

export type BankingWorkspace = {
  accounts: Array<{
    id: string; name: string; institution_name: string | null; account_type: string;
    last_four: string | null; currency: string; status: string; notes: string | null;
    unmatched_transaction_count: number; created_at: string;
  }>;
  imports: Array<{
    id: string; bank_account_id: string; file_name: string; status: string; total_rows: number;
    imported_rows: number; invalid_rows: number; duplicate_rows: number;
    statement_start_on: string | null; statement_end_on: string | null;
    opening_balance_cents: number | null; closing_balance_cents: number | null;
    malware_scan_status: string; completed_at: string | null; created_at: string;
  }>;
  transactions: Array<{
    id: string; bank_account_id: string; statement_import_id: string; occurred_on: string;
    posted_on: string | null; description: string; amount_cents: number; balance_cents: number | null;
    status: string; journal_entry_id: string | null; journal_entry_number: string | null; notes: string | null;
  }>;
  reconciliations: Array<{
    id: string; bank_account_id: string; statement_import_id: string | null;
    statement_start_on: string; statement_end_on: string; opening_balance_cents: number;
    closing_balance_cents: number; calculated_closing_balance_cents: number; difference_cents: number;
    status: string; matched_transaction_count: number; unresolved_transaction_count: number;
    approved_at: string | null; notes: string | null;
  }>;
  posted_journals: Array<{ id: string; entry_number: string; memo: string; cash_delta_cents: number }>;
  summary: { active_accounts: number; unmatched_transactions: number; unreconciled_imports: number; open_reconciliations: number };
};

export type AccountingReports = {
  period_start_on: string;
  period_end_on: string;
  accounting_method: string;
  profit_and_loss: {
    revenue: AccountingReportSection;
    cost_of_revenue: AccountingReportSection;
    operating_expenses: AccountingReportSection;
    gross_profit_cents: number;
    net_income_cents: number;
  };
  balance_sheet: {
    assets: AccountingReportSection;
    liabilities: AccountingReportSection;
    equity: AccountingReportSection;
    current_earnings_cents: number;
    total_assets_cents: number;
    total_liabilities_and_equity_cents: number;
    balanced: boolean;
  };
  cash_flow: {
    operating_cents: number;
    investing_cents: number;
    financing_cents: number;
    net_change_cents: number;
  };
  trial_balance: {
    total_debits_cents: number;
    total_credits_cents: number;
    balanced: boolean;
    lines: AccountingReportLine[];
  };
  general_ledger: Array<{
    journal_entry_id: string;
    entry_number: string;
    entry_date: string;
    memo: string;
    source_type: string;
    source_id: string | null;
    evidence_references: string[];
    account_code: string;
    account_name: string;
    debit_cents: number;
    credit_cents: number;
    deal_id: string | null;
    transaction_id: string | null;
  }>;
  receivables: Array<{
    id: string;
    source: string;
    amount_cents: number;
    status: string;
    expected_on: string;
    lead_id: string | null;
    deal_id: string | null;
    transaction_id: string | null;
  }>;
  payables: Array<{
    id: string;
    category: string;
    counterparty: string;
    amount_cents: number;
    status: string;
    due_on: string | null;
    source_id: string | null;
  }>;
  payments: Array<{
    id: string;
    category: string;
    counterparty: string;
    amount_cents: number;
    paid_on: string;
    payment_reference: string | null;
    source_id: string | null;
  }>;
  deal_profitability: Array<{
    deal_id: string;
    revenue_cents: number;
    cost_cents: number;
    profit_cents: number;
  }>;
  close_readiness: {
    period_key: string;
    period_status: string;
    ready_to_close: boolean;
    blocking_count: number;
    warning_count: number;
    items: Array<{
      key: string;
      label: string;
      status: string;
      detail: string;
      action_href: string;
    }>;
  };
};

export type AccountingReportLine = {
  account_id: string;
  code: string;
  name: string;
  account_type: string;
  opening_balance_cents: number;
  debit_cents: number;
  credit_cents: number;
  ending_balance_cents: number;
  journal_count: number;
};

export type AccountingReportSection = {
  key: string;
  label: string;
  total_cents: number;
  lines: AccountingReportLine[];
};

export type MarketingSummary = {
  total_spend_cents: number;
  collected_revenue_cents: number;
  leads_created: number;
  address_leads: number;
  contact_completed_leads: number;
  address_to_contact_rate_basis_points: number | null;
  contracted_leads: number;
  cost_per_lead_cents: number | null;
  cost_per_address_lead_cents: number | null;
  cost_per_contact_completed_lead_cents: number | null;
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
    address_leads: number;
    contact_completed_leads: number;
    address_to_contact_rate_basis_points: number | null;
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
  measurement: {
    mode: string;
    attribution_model: string;
    attribution_window_days: number;
    policy_version: string;
    providers: Array<{
      platform: string;
      configured: boolean;
      blockers: string[];
      delivery_mode: string | null;
      test_mode_enabled: boolean | null;
      pixel_id_fingerprint: string | null;
      access_token_present: boolean | null;
    }>;
    event_counts: Record<string, number>;
    worker: {
      status: string;
      required: boolean;
      heartbeat_at: string | null;
      consecutive_failures: number;
      current_operation: string | null;
      marketing_conversion_mode: string | null;
      meta_pixel_id_fingerprint: string | null;
      meta_test_mode_enabled: boolean | null;
      meta_configured: boolean | null;
      meta_configuration_blockers: string[];
      meta_access_token_present: boolean | null;
    };
    meta_match_coverage: Array<{
      event_name: string;
      total: number;
      fbp_count: number;
      fbc_count: number;
      client_ip_count: number;
      client_user_agent_count: number;
      fbp_basis_points: number | null;
      fbc_basis_points: number | null;
      client_ip_basis_points: number | null;
      client_user_agent_basis_points: number | null;
    }>;
    meta_match_coverage_window_days: number;
    oldest_meta_pending_at: string | null;
  };
  campaigns: Array<{
    source: string;
    medium: string;
    campaign: string;
    page_views: number;
    form_starts: number;
    form_abandons: number;
    form_submits: number;
    address_leads: number;
    contact_completed_leads: number;
    address_to_contact_rate_basis_points: number | null;
    call_clicks: number;
    leads_created: number;
    contracted_leads: number;
    collected_revenue_cents: number;
    marketing_spend_cents: number;
    cost_per_lead_cents: number | null;
    cost_per_address_lead_cents: number | null;
    cost_per_contact_completed_lead_cents: number | null;
    cost_per_contract_cents: number | null;
    return_on_ad_spend_basis_points: number | null;
  }>;
  offline_exports: Array<{
    id: string;
    platform: string;
    conversion_event_id: string | null;
    lead_id: string | null;
    revenue_record_id: string | null;
    event_key: string;
    source_record_type: string;
    source_record_id: string;
    event_name: string;
    occurred_at: string;
    attribution_model: string;
    consent_basis: string;
    masked_click_id: string;
    click_id_type: string;
    value_cents: number | null;
    currency: string;
    delivery_mode: string;
    status: string;
    attempt_count: number;
    last_attempt_at: string | null;
    next_attempt_at: string | null;
    exported_at: string | null;
    provider_request_id: string | null;
    provider_accepted_count: number | null;
    provider_warnings: string[];
    last_error: string | null;
    created_at: string;
  }>;
};

export type MarketingExperimentVariant = {
  key: string;
  label: string;
  weight_basis_points: number;
  cta_label: string;
};

export type MarketingExperimentPerformance = {
  key: string;
  label: string;
  cta_label: string;
  assigned_sessions: number;
  desktop_sessions: number;
  tablet_sessions: number;
  mobile_sessions: number;
  form_starts: number;
  form_submits: number;
  leads_created: number;
  qualified_leads: number;
  appointments_scheduled: number;
  contracts_signed: number;
  funded_deals: number;
  collected_revenue_cents: number;
  primary_outcomes: number;
  primary_rate_basis_points: number | null;
  source_breakdown: Array<{
    source: string;
    medium: string;
    campaign: string;
    assigned_sessions: number;
    leads_created: number;
    qualified_leads: number;
    contracts_signed: number;
    funded_deals: number;
    collected_revenue_cents: number;
  }>;
};

export type MarketingExperiment = {
  id: string;
  experiment_key: string;
  name: string;
  hypothesis: string;
  surface_key: string;
  primary_metric:
    | "form_submit"
    | "qualified_lead"
    | "appointment_scheduled"
    | "contract_signed"
    | "funded_deal";
  variants: MarketingExperimentVariant[];
  minimum_sessions_per_variant: number;
  minimum_runtime_days: number;
  decision_rule: string;
  status: "draft" | "running" | "paused" | "completed";
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  decision_notes: string | null;
  runtime_days: number;
  decision_status: string;
  decision_blockers: string[];
  performance: MarketingExperimentPerformance[];
  created_at: string;
  updated_at: string;
};

export type MarketingExperimentOverview = {
  can_manage: boolean;
  experiments: MarketingExperiment[];
};

export type TrustProofRecord = {
  id: string;
  proof_type: "review" | "seller_story" | "completed_purchase" | "statistic";
  title: string;
  content: string | null;
  attribution_name: string | null;
  attribution_detail: string | null;
  location_label: string | null;
  rating: number | null;
  metric_label: string | null;
  metric_value: string | null;
  methodology: string | null;
  as_of_date: string | null;
  source_type: string;
  source_url: string | null;
  source_reference: string | null;
  show_source_link: boolean;
  permission_status: "pending" | "granted" | "not_required" | "revoked";
  permission_evidence_notes: string | null;
  material_connection: string | null;
  disclosure: string | null;
  publication_status: "draft" | "in_review" | "published" | "retired";
  featured: boolean;
  sort_order: number;
  created_by_name: string;
  updated_by_name: string;
  approved_by_name: string | null;
  approved_at: string | null;
  published_at: string | null;
  retired_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TrustProofOverview = {
  can_manage: boolean;
  records: TrustProofRecord[];
};

export type PublicTrustProof = {
  id: string;
  proof_type: "review" | "seller_story" | "completed_purchase" | "statistic";
  title: string;
  content: string | null;
  attribution_name: string | null;
  attribution_detail: string | null;
  location_label: string | null;
  rating: number | null;
  metric_label: string | null;
  metric_value: string | null;
  methodology: string | null;
  as_of_date: string | null;
  source_type: string;
  source_url: string | null;
  disclosure: string | null;
  featured: boolean;
  published_at: string;
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
    automation: {
      phase_status: string;
      external_delivery_globally_enabled: boolean;
      emergency_stop: boolean;
      metrics: {
        policy_count: number;
        control_only_count: number;
        paused_count: number;
        canary_ready_count: number;
        external_delivery_enabled_count: number;
        simulation_count: number;
        blocked_simulation_count: number;
        external_delivery_attempt_count: number;
        delivered_message_count: number;
      };
      policies: Array<{
        id: string;
        action_key: string;
        name: string;
        description: string;
        capability_key: string;
        channel: string;
        provider_key: string;
        owner_role_key: string;
        status: string;
        audience_policy: Record<string, unknown>;
        consent_policy: Record<string, unknown>;
        template_policy: Record<string, unknown>;
        schedule_policy: Record<string, unknown>;
        volume_policy: Record<string, unknown>;
        cost_policy: Record<string, unknown>;
        quality_policy: Record<string, unknown>;
        canary_policy: Record<string, unknown>;
        pause_policy: Record<string, unknown>;
        rollback_policy: Record<string, unknown>;
        prohibited_actions: string[];
        dry_run_only: boolean;
        external_delivery_enabled: boolean;
        approved_by_user_id: string | null;
        approved_at: string | null;
        last_pause_reason: string | null;
        paused_at: string | null;
        readiness_status: string;
        readiness_blockers: string[];
        attempts: Array<{
          id: string;
          policy_id: string;
          idempotency_key: string;
          execution_mode: string;
          status: string;
          audience_count: number;
          estimated_cost_microusd: number;
          policy_checks: Record<string, unknown>;
          block_reasons: string[];
          external_delivery_attempted: boolean;
          delivered_count: number;
          requested_by_user_id: string;
          created_at: string;
        }>;
        updated_at: string;
      }>;
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
  provider: string;
  methodology_version: string | null;
  confidence_score: number;
  comp_review_applied: boolean;
  evidence_reference: string | null;
  notes: string | null;
  validation_scenarios: string[];
  recorded_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type UnderwritingCalibrationMetric = {
  market_key: string;
  providers: string[];
  methodology_versions: string[];
  sample_count: number;
  median_error_percentage: number | null;
  median_absolute_error_percentage: number | null;
  range_coverage_percentage: number | null;
  overestimate_count: number;
  underestimate_count: number;
  balanced_count: number;
  repair_sample_count: number;
  repair_median_absolute_error_percentage: number | null;
  seller_contract_sample_count: number;
  seller_contract_median_absolute_variance_percentage: number | null;
  disposition_sample_count: number;
  disposition_median_absolute_error_percentage: number | null;
  comp_review_case_count: number;
  comp_review_decision_count: number;
  comp_review_override_count: number;
  comp_review_override_percentage: number | null;
  provider_adequacy: string;
  failure_patterns: string[];
  readiness: string;
};

export type UnderwritingCalibrationSegment = {
  dimension: string;
  segment_key: string;
  sample_count: number;
  median_absolute_error_percentage: number | null;
  range_coverage_percentage: number | null;
  repair_sample_count: number;
  repair_median_absolute_error_percentage: number | null;
  comp_review_override_percentage: number | null;
};

export type UnderwritingCalibrationDecision = {
  id: string;
  scope_key: string;
  decision_type: string;
  status: string;
  title: string;
  rationale: string;
  current_methodology_version: string | null;
  proposed_methodology_version: string | null;
  proposed_changes: Record<string, unknown>;
  evidence_snapshot: Record<string, unknown>;
  sample_count: number;
  minimum_sample_required: number;
  approval_blocked: boolean;
  proposed_by_user_id: string | null;
  decided_by_user_id: string | null;
  decision_notes: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type UnderwritingBaseline = {
  analysis_count: number;
  instrumented_analysis_count: number;
  methodology_versions: string[];
  median_duration_ms: number | null;
  median_provider_returned_comp_count: number | null;
  median_candidate_comp_count: number | null;
  median_selected_comp_count: number | null;
  median_comp_yield_percentage: number | null;
  market_data_reuse_count: number;
  market_data_reuse_percentage: number | null;
  manual_review_required_count: number;
  manual_review_required_percentage: number | null;
  comp_review_case_count: number;
  comp_review_decision_count: number;
  comp_review_override_count: number;
  comp_review_override_percentage: number | null;
  ai_scope_review_count: number;
  ai_scope_correction_count: number;
  ai_scope_correction_percentage: number | null;
  repair_catalog_case_count: number;
  repair_catalog_median_absolute_error_percentage: number | null;
};

export type UnderwritingShadowReplayMetric = {
  scope_key: string;
  paired_case_count: number;
  baseline_median_absolute_error_percentage: number | null;
  shadow_median_absolute_error_percentage: number | null;
  median_improvement_percentage_points: number | null;
  shadow_win_count: number;
  tie_count: number;
  baseline_win_count: number;
  shadow_supported_count: number;
  shadow_partial_count: number;
  shadow_unsupported_count: number;
  unsafe_certainty_count: number;
};

export type UnderwritingShadowReplayCase = {
  analysis_id: string;
  lead_id: string;
  property_address: string;
  market_key: string;
  benchmark_arv_cents: number;
  baseline_arv_cents: number;
  shadow_arv_cents: number;
  baseline_absolute_error_percentage: number;
  shadow_absolute_error_percentage: number;
  improvement_percentage_points: number;
  winner: "v2.2" | "v3_shadow" | "tie";
  shadow_status: string;
  shadow_confidence_score: number | null;
  validation_scenarios: string[];
  risk_flags: string[];
};

export type UnderwritingRolloutGate = {
  key: string;
  label: string;
  status: "passed" | "blocked" | "pending";
  current_value: string;
  required_value: string;
  detail: string;
};

export type UnderwritingShadowValidation = {
  active_methodology_version: string;
  shadow_methodology_version: string;
  rollout_status: string;
  activation_allowed: boolean;
  rollback_available: boolean;
  human_authority_required: boolean;
  overall: UnderwritingShadowReplayMetric;
  markets: UnderwritingShadowReplayMetric[];
  cases: UnderwritingShadowReplayCase[];
  gates: UnderwritingRolloutGate[];
  scenario_coverage: Record<string, number>;
  approved_rollout_decision_id: string | null;
};

export type UnderwritingCalibration = {
  baseline?: UnderwritingBaseline;
  overall: UnderwritingCalibrationMetric;
  markets: UnderwritingCalibrationMetric[];
  provider_scorecards: UnderwritingCalibrationMetric[];
  segments: UnderwritingCalibrationSegment[];
  shadow_validation: UnderwritingShadowValidation;
  cases: UnderwritingCalibrationCase[];
  decisions: UnderwritingCalibrationDecision[];
  uncalibrated_analysis_count: number;
  minimum_sample_for_formula_review: number;
  automatic_formula_changes_enabled: boolean;
};

export type SpeedToLeadTask = {
  task_id: string;
  lead_id: string | null;
  deal_id: string | null;
  task_type: string;
  work_kind: string;
  title: string;
  seller_name: string | null;
  property_address: string | null;
  source: string | null;
  stage_key: string | null;
  priority: string;
  status: string;
  due_at: string | null;
  created_at: string;
  completed_at: string | null;
  assigned_user_id: string | null;
  assigned_user_email: string | null;
  due_status: string;
};

export type TaskWorkspaceItem = {
  id: string;
  item_type: "task" | "approval" | "ai_work";
  work_kind:
    | "primary_next_action"
    | "supporting"
    | "operational_exception"
    | "approval"
    | "ai_in_progress"
    | "ai_review"
    | "ai_completed";
  source_record_type: string;
  source_record_id: string | null;
  source_record_label: string;
  source_record_detail: string | null;
  source_url: string | null;
  task_id: string | null;
  approval_id: string | null;
  ai_event_id: string | null;
  ai_run_id: string | null;
  capability_key: string | null;
  ai_output: Record<string, unknown>;
  task_type: string;
  title: string;
  summary: string | null;
  status: string;
  priority: string;
  due_at: string | null;
  due_status: "overdue" | "today" | "upcoming" | "unscheduled" | "completed";
  created_at: string;
  completed_at: string | null;
  assigned_user_id: string | null;
  assigned_user_name: string | null;
  assigned_user_email: string | null;
  outcome: string | null;
  completion_notes: string | null;
  attention_flags: string[];
  can_complete: boolean;
  can_decide: boolean;
  review_url: string | null;
  approval_metadata: Record<string, unknown>;
};

export type TaskWorkspace = {
  items: TaskWorkspaceItem[];
  can_manage_team: boolean;
  can_decide_approvals: boolean;
  current_user_id: string;
  current_user_email: string;
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
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  owner_options: BuyerRelationshipOwner[];
  source_options: string[];
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

export type DealQueueItem = {
  id: string;
  lead_id: string;
  transaction_id: string;
  disposition_case_id: string | null;
  seller_name: string;
  property_address: string;
  property_type: string | null;
  stage_key: string;
  contract_status: string;
  closing_status: string;
  disposition_status: string;
  finance_status: string;
  owner_name: string | null;
  coordinator_name: string | null;
  disposition_owner_name: string | null;
  closing_date: string | null;
  next_deadline: string | null;
  checklist_complete: number;
  checklist_total: number;
  document_count: number;
  buyer_match_count: number;
  buyer_offer_count: number;
  selected_buyer_name: string | null;
  contract_price_cents: number;
  assignment_fee_cents: number | null;
  company_profit_cents: number | null;
  company_margin_basis_points: number | null;
  primary_next_action: null | {
    task_id: string;
    title: string;
    action_type: string;
    due_at: string | null;
    responsible_user_id: string | null;
    responsible_user_email: string | null;
    due_status: string;
  };
  blockers: Array<{
    key: string;
    domain: string;
    label: string;
    severity: string;
  }>;
  created_at: string;
};

export type DealOverview = {
  can_view_economics: boolean;
  metrics: {
    active: number;
    closing_exceptions: number;
    ready_for_disposition: number;
    buyer_needed: number;
    finance_review: number;
    completed: number;
  };
  items: DealQueueItem[];
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

export type EsignEnvelope = {
  id: string;
  contract_package_id: string;
  provider: string;
  provider_document_id: string;
  delivery_mode: string;
  status: string;
  subject: string;
  message: string | null;
  test_mode: boolean;
  completed_document_id: string | null;
  sent_at: string | null;
  completed_at: string | null;
  declined_at: string | null;
  expired_at: string | null;
  cancelled_at: string | null;
  recipients: Array<{
    id: string;
    placeholder_name: string;
    name: string;
    email: string;
    signing_order: number;
    status: string;
    viewed_at: string | null;
    signed_at: string | null;
    declined_at: string | null;
  }>;
  embedded_signers: Array<{
    recipient_id: string;
    placeholder_name: string;
    name: string;
    email: string;
    signing_order: number;
    signing_url: string;
  }>;
  created_at: string;
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
    document_type: string;
    status: string;
    seller_name: string;
    buyer_entity_name: string;
    assignee_name: string | null;
    assignee_email: string | null;
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
  esign_envelopes: EsignEnvelope[];
  documents: Array<{
    id: string;
    contract_package_id: string | null;
    document_type: string;
    title: string;
    status: string;
    file_name: string;
    content_type: string;
    file_size: number;
    storage_provider: string;
    malware_scan_status: string;
    retention_until: string | null;
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

export type F4IntegrationStatus = {
  storage_provider: string;
  storage_configured: boolean;
  storage_blockers: string[];
  malware_scanner: string;
  malware_scan_required: boolean;
  esign_provider: string;
  esign_configured: boolean;
  esign_test_mode: boolean;
  esign_blockers: string[];
  esign_account_connected: boolean;
  esign_account_email: string | null;
  esign_webhook_connected: boolean;
  esign_webhook_callback_url: string;
  esign_last_verified_at: string | null;
  esign_linked_template_count: number;
  esign_ready_template_count: number;
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

export async function getTaskWorkspace(): Promise<{
  workspace: TaskWorkspace | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/tasks/workspace`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      workspace: (await response.json()) as TaskWorkspace,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate task workspace request failed.", error);
    return { workspace: null, apiConnected: false };
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

export async function getClosedLeads({
  limit = 101,
  offset = 0,
  q = "",
}: {
  limit?: number;
  offset?: number;
  q?: string;
} = {}): Promise<{
  leads: LeadListItem[];
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const query = new URLSearchParams({
    closed: "true",
    limit: String(limit),
    offset: String(offset),
  });
  if (q.trim()) query.set("q", q.trim());

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/leads?${query.toString()}`, {
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
    console.error("Stonegate closed leads request failed.", error);
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

export async function getMyRoleSetup(): Promise<{
  roleSetup: MyRoleSetup | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/operating-model/my-setup`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      roleSetup: (await response.json()) as MyRoleSetup,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate role setup request failed.", error);
    return { roleSetup: null, apiConnected: false };
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

export async function getProspectingDialerContext(): Promise<{
  dialerContext: ProspectingDialerContext | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/prospecting/dialer/context`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      dialerContext: (await response.json()) as ProspectingDialerContext,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate native dialer context request failed.", error);
    return { dialerContext: null, apiConnected: false };
  }
}

export async function getProspectingDialerOperations(): Promise<{
  dialerOperations: ProspectingDialerOperations | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/dialer/operations`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      dialerOperations: (await response.json()) as ProspectingDialerOperations,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate dialer operations request failed.", error);
    return { dialerOperations: null, apiConnected: false };
  }
}

export async function getProspectingDialerPilot(): Promise<{
  dialerPilot: ProspectingDialerPilotOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/dialer/pilot`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      dialerPilot: (await response.json()) as ProspectingDialerPilotOverview,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate controlled dialer pilot request failed.", error);
    return { dialerPilot: null, apiConnected: false };
  }
}

export async function getProspectingDialerAnalytics(
  query: ProspectingDialerAnalyticsQuery = {},
): Promise<{
  dialerAnalytics: ProspectingDialerAnalytics | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value) search.set(key, value);
  }
  const suffix = search.size ? `?${search.toString()}` : "";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/dialer/analytics${suffix}`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      dialerAnalytics: (await response.json()) as ProspectingDialerAnalytics,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate dialer analytics request failed.", error);
    return { dialerAnalytics: null, apiConnected: false };
  }
}

export async function getBatchDialerVaPerformance(
  query: BatchDialerVaPerformanceQuery = {},
): Promise<{
  vaPerformance: BatchDialerVaPerformance | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value) search.set(key, value);
  }
  const suffix = search.size ? `?${search.toString()}` : "";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/batchdialer/va-performance${suffix}`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      vaPerformance: (await response.json()) as BatchDialerVaPerformance,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate BatchDialer VA performance request failed.", error);
    return { vaPerformance: null, apiConnected: false };
  }
}

export async function getBatchDialerAgentMappings(): Promise<{
  agentMappings: BatchDialerAgentMappings | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/batchdialer/agent-mappings`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      agentMappings: (await response.json()) as BatchDialerAgentMappings,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate BatchDialer agent mapping request failed.", error);
    return { agentMappings: null, apiConnected: false };
  }
}

export async function getBatchDialerCampaignMappings(): Promise<{
  campaignMappings: BatchDialerCampaignMappings | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/batchdialer/campaign-mappings`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      campaignMappings: (await response.json()) as BatchDialerCampaignMappings,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate BatchDialer campaign mapping request failed.", error);
    return { campaignMappings: null, apiConnected: false };
  }
}

export async function getProspectingInboundCallbacks(): Promise<{
  callbacks: ProspectingInboundCallbackList | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/prospecting/dialer/callbacks`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return {
      callbacks: (await response.json()) as ProspectingInboundCallbackList,
      apiConnected: true,
    };
  } catch (error) {
    console.error("Stonegate prospecting callback request failed.", error);
    return { callbacks: null, apiConnected: false };
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

export async function getFieldAppointmentWorkspace(
  appointmentId: string,
): Promise<FieldAppointmentWorkspace | null> {
  if (!appointmentId) return null;
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/field-operations/appointments/${encodeURIComponent(
        appointmentId,
      )}/workspace`,
      {
        headers,
        cache: "no-store",
      },
    );
    if (!response.ok) {
      throw await apiError(response);
    }
    return (await response.json()) as FieldAppointmentWorkspace;
  } catch (error) {
    console.error("Stonegate appointment workspace request failed.", error);
    return null;
  }
}

export async function getBuyers(query: BuyerQuery = {}): Promise<BuyerPage> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const page = Number.isFinite(query.page) ? Math.max(1, Math.floor(query.page ?? 1)) : 1;
  const pageSize = Number.isFinite(query.pageSize)
    ? Math.min(100, Math.max(10, Math.floor(query.pageSize ?? 25)))
    : 25;
  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String((page - 1) * pageSize),
  });
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.assetClass?.trim()) params.set("asset_class", query.assetClass.trim());
  if (query.status?.trim()) params.set("status", query.status.trim());
  if (query.ownerUserId?.trim()) {
    params.set("owner_id", query.ownerUserId.trim());
  }
  if (query.sourceKey?.trim()) params.set("source_key", query.sourceKey.trim());

  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/buyers?${params.toString()}`, {
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      throw await apiError(response);
    }

    const payload = (await response.json()) as BuyerListResponse;
    return {
      buyers: payload.items,
      total: payload.total,
      page: Math.floor(payload.offset / Math.max(1, payload.limit)) + 1,
      pageSize: payload.limit,
      hasMore: payload.has_more,
      relationshipOwners: payload.owner_options,
      sourceOptions: payload.source_options,
      apiConnected: true,
      errorMessage: null,
    };
  } catch (error) {
    return {
      buyers: [],
      total: 0,
      page,
      pageSize,
      hasMore: false,
      relationshipOwners: [],
      sourceOptions: [],
      apiConnected: false,
      errorMessage: error instanceof Error ? error.message : "Buyer CRM is unavailable.",
    };
  }
}

export async function getBuyer(buyerId: string): Promise<BuyerListItem | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/buyers/${encodeURIComponent(buyerId)}`,
      { headers: await getServerApiHeaders(), cache: "no-store" },
    );
    if (!response.ok) throw await apiError(response);
    return (await response.json()) as BuyerListItem;
  } catch (error) {
    console.error("Stonegate buyer detail request failed.", error);
    return null;
  }
}

export async function getBuyerProfile(buyerId: string): Promise<{
  profile: BuyerProfile | null;
  errorMessage: string | null;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/buyers/${encodeURIComponent(buyerId)}/profile`,
      { headers: await getServerApiHeaders(), cache: "no-store" },
    );
    if (!response.ok) throw await apiError(response);
    return {
      profile: (await response.json()) as BuyerProfile,
      errorMessage: null,
    };
  } catch (error) {
    console.error("Stonegate buyer profile request failed.", error);
    return {
      profile: null,
      errorMessage:
        error instanceof Error ? error.message : "Buyer history is temporarily unavailable.",
    };
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

export async function getAccountingSetup(): Promise<AccountingSetup | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/finance/accounting/setup`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as AccountingSetup;
  } catch {
    return null;
  }
}

export async function getAccountingLedger(): Promise<AccountingLedger | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/finance/accounting/ledger`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as AccountingLedger;
  } catch {
    return null;
  }
}

export async function getAccountingOperations(): Promise<AccountingOperations | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}/api/v1/finance/accounting/operations`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) return null;
    return (await response.json()) as AccountingOperations;
  } catch {
    return null;
  }
}

export async function getVendorAccounting(): Promise<VendorAccounting | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/finance/vendor-accounting`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as VendorAccounting;
  } catch {
    return null;
  }
}

export async function getBankingWorkspace(): Promise<BankingWorkspace | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(`${apiBaseUrl}/api/v1/finance/banking`, { headers, cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as BankingWorkspace;
  } catch {
    return null;
  }
}

export async function getAccountingReports(
  requestedStartOn?: string,
  requestedEndOn?: string,
): Promise<AccountingReports | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const today = new Date().toISOString().slice(0, 10);
  const startOn = requestedStartOn ?? `${today.slice(0, 8)}01`;
  const endOn = requestedEndOn ?? today;
  try {
    const headers = await getServerApiHeaders();
    const query = new URLSearchParams({ start_on: startOn, end_on: endOn });
    const response = await fetch(
      `${apiBaseUrl}/api/v1/finance/accounting/reports?${query}`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) return null;
    return (await response.json()) as AccountingReports;
  } catch {
    return null;
  }
}

async function getManagementCopilot(
  path: string,
  periodDays: number,
): Promise<ManagementCopilotOverview | null> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const headers = await getServerApiHeaders();
    const response = await fetch(
      `${apiBaseUrl}${path}?period_days=${periodDays}`,
      { headers, cache: "no-store" },
    );
    if (!response.ok) return null;
    return (await response.json()) as ManagementCopilotOverview;
  } catch {
    return null;
  }
}

export function getFinanceCopilotOverview(periodDays: number) {
  return getManagementCopilot("/api/v1/finance/copilot", periodDays);
}

export function getTaxCopilotOverview(periodDays: number) {
  return getManagementCopilot("/api/v1/finance/tax-copilot", periodDays);
}

export function getMarketingCopilotOverview(periodDays: number) {
  return getManagementCopilot("/api/v1/marketing/copilot", periodDays);
}

export function getExecutiveCopilotOverview(periodDays = 30) {
  return getManagementCopilot("/api/v1/dashboard/executive-copilot", periodDays);
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
    address_leads: 0,
    contact_completed_leads: 0,
    address_to_contact_rate_basis_points: null,
    contracted_leads: 0,
    cost_per_lead_cents: null,
    cost_per_address_lead_cents: null,
    cost_per_contact_completed_lead_cents: null,
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
    address_leads: 0,
    contact_completed_leads: 0,
    address_to_contact_rate_basis_points: null,
    submit_errors: 0,
    form_abandons: 0,
    start_to_submit_rate_basis_points: null,
  },
  web_vitals: [],
  measurement: {
    mode: "disabled",
    attribution_model: "last_eligible_platform_click",
    attribution_window_days: 90,
    policy_version: "stonegate-marketing-measurement-v1",
    providers: [],
    event_counts: {},
    worker: {
      status: "missing",
      required: false,
      heartbeat_at: null,
      consecutive_failures: 0,
      current_operation: null,
      marketing_conversion_mode: null,
      meta_pixel_id_fingerprint: null,
      meta_test_mode_enabled: null,
      meta_configured: null,
      meta_configuration_blockers: [],
      meta_access_token_present: null,
    },
    meta_match_coverage: [],
    meta_match_coverage_window_days: 30,
    oldest_meta_pending_at: null,
  },
  campaigns: [],
  offline_exports: [],
};

function safeMarketingCost(spendCents: number, count: number) {
  return count > 0 ? Math.round(spendCents / count) : null;
}

function safeMarketingRate(numerator: number, denominator: number) {
  return denominator > 0 ? Math.round((numerator / denominator) * 10_000) : null;
}

function normalizeMarketingOverview(value: MarketingOverview): MarketingOverview {
  // The API and web services can finish a Render deployment a few minutes apart.
  // Keep the Marketing workspace usable while an older API response is still live.
  const measurement = value.measurement ?? emptyMarketingOverview.measurement;
  const campaigns = (value.campaigns ?? []).map((item) => {
    const addressLeads = item.address_leads ?? 0;
    const contactCompletedLeads = item.contact_completed_leads ?? 0;
    return {
      ...item,
      source: item.source?.trim() || "direct",
      medium: item.medium?.trim() || "unknown",
      campaign: item.campaign?.trim() || "uncategorized",
      address_leads: addressLeads,
      contact_completed_leads: contactCompletedLeads,
      address_to_contact_rate_basis_points:
        item.address_to_contact_rate_basis_points ??
        safeMarketingRate(contactCompletedLeads, addressLeads),
      cost_per_address_lead_cents:
        item.cost_per_address_lead_cents ??
        safeMarketingCost(item.marketing_spend_cents, addressLeads),
      cost_per_contact_completed_lead_cents:
        item.cost_per_contact_completed_lead_cents ??
        safeMarketingCost(item.marketing_spend_cents, contactCompletedLeads),
    };
  });
  const summary = value.summary ?? emptyMarketingOverview.summary;
  const summaryAddressLeads = summary.address_leads ?? 0;
  const summaryContactCompletedLeads =
    summary.contact_completed_leads ??
    campaigns.reduce((total, item) => total + item.contact_completed_leads, 0);
  const publicFunnel = value.public_funnel ?? emptyMarketingOverview.public_funnel;
  const funnelAddressLeads = publicFunnel.address_leads ?? 0;
  const funnelContactCompletedLeads =
    publicFunnel.contact_completed_leads ?? 0;
  const coverageByName = new Map(
    (measurement.meta_match_coverage ?? []).map((item) => [item.event_name, item]),
  );
  const canonicalCoverage = ["all", "ViewContent", "Lead", "Contact"].map(
    (eventName) =>
      coverageByName.get(eventName) ?? {
        event_name: eventName,
        total: 0,
        fbp_count: 0,
        fbc_count: 0,
        client_ip_count: 0,
        client_user_agent_count: 0,
        fbp_basis_points: null,
        fbc_basis_points: null,
        client_ip_basis_points: null,
        client_user_agent_basis_points: null,
      },
  );
  return {
    ...value,
    summary: {
      ...emptyMarketingOverview.summary,
      ...summary,
      address_leads: summaryAddressLeads,
      contact_completed_leads: summaryContactCompletedLeads,
      address_to_contact_rate_basis_points:
        summary.address_to_contact_rate_basis_points ??
        safeMarketingRate(summaryContactCompletedLeads, summaryAddressLeads),
      cost_per_address_lead_cents:
        summary.cost_per_address_lead_cents ??
        safeMarketingCost(summary.total_spend_cents, summaryAddressLeads),
      cost_per_contact_completed_lead_cents:
        summary.cost_per_contact_completed_lead_cents ??
        safeMarketingCost(summary.total_spend_cents, summaryContactCompletedLeads),
    },
    previous_summary: value.previous_summary
      ? {
          ...emptyMarketingOverview.summary,
          ...value.previous_summary,
          address_leads: value.previous_summary.address_leads ?? 0,
          contact_completed_leads: value.previous_summary.contact_completed_leads ?? 0,
          address_to_contact_rate_basis_points:
            value.previous_summary.address_to_contact_rate_basis_points ?? null,
          cost_per_address_lead_cents:
            value.previous_summary.cost_per_address_lead_cents ?? null,
          cost_per_contact_completed_lead_cents:
            value.previous_summary.cost_per_contact_completed_lead_cents ?? null,
        }
      : null,
    public_funnel: {
      ...emptyMarketingOverview.public_funnel,
      ...publicFunnel,
      address_leads: funnelAddressLeads,
      contact_completed_leads: funnelContactCompletedLeads,
      address_to_contact_rate_basis_points:
        publicFunnel.address_to_contact_rate_basis_points ??
        safeMarketingRate(funnelContactCompletedLeads, funnelAddressLeads),
    },
    measurement: {
      ...emptyMarketingOverview.measurement,
      ...measurement,
      worker: {
        ...emptyMarketingOverview.measurement.worker,
        ...(measurement.worker ?? {}),
      },
      meta_match_coverage: canonicalCoverage,
      meta_match_coverage_window_days:
        measurement.meta_match_coverage_window_days ?? 30,
      oldest_meta_pending_at: measurement.oldest_meta_pending_at ?? null,
    },
    campaigns,
    offline_exports: (value.offline_exports ?? []).map((item) => ({
      ...item,
      provider_accepted_count: item.provider_accepted_count ?? null,
      provider_warnings: Array.isArray(item.provider_warnings)
        ? item.provider_warnings
        : [],
    })),
  };
}

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

    return {
      marketing: normalizeMarketingOverview((await response.json()) as MarketingOverview),
      apiConnected: true,
    };
  } catch {
    return { marketing: emptyMarketingOverview, apiConnected: false };
  }
}

export async function getMarketingExperimentOverview(): Promise<{
  experimentOverview: MarketingExperimentOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/marketing/experiments`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      experimentOverview: (await response.json()) as MarketingExperimentOverview,
      apiConnected: true,
    };
  } catch {
    return {
      experimentOverview: { can_manage: false, experiments: [] },
      apiConnected: false,
    };
  }
}

export async function getTrustProofOverview(): Promise<{
  trustProof: TrustProofOverview;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/marketing/trust-proofs`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      trustProof: (await response.json()) as TrustProofOverview,
      apiConnected: true,
    };
  } catch {
    return {
      trustProof: { can_manage: false, records: [] },
      apiConnected: false,
    };
  }
}

export async function getPublicTrustProof(): Promise<PublicTrustProof[]> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/public/trust-proofs`, {
      next: { revalidate: 300 },
    });
    if (!response.ok) throw new Error("Public proof API returned a non-OK response.");
    return ((await response.json()) as { records: PublicTrustProof[] }).records;
  } catch {
    return [];
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
    automation: {
      phase_status: "not_installed",
      external_delivery_globally_enabled: false,
      emergency_stop: false,
      metrics: {
        policy_count: 0,
        control_only_count: 0,
        paused_count: 0,
        canary_ready_count: 0,
        external_delivery_enabled_count: 0,
        simulation_count: 0,
        blocked_simulation_count: 0,
        external_delivery_attempt_count: 0,
        delivered_message_count: 0,
      },
      policies: [],
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

export async function getDealOverview(): Promise<{
  deals: DealOverview | null;
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/deals`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      deals: (await response.json()) as DealOverview,
      apiConnected: true,
    };
  } catch {
    return { deals: null, apiConnected: false };
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

export async function getDispositionDesk(
  scope: DispositionDeskScope = "mine",
  section?: DispositionDeskCategory,
  offset = 0,
): Promise<{
  desk: DispositionDeskOverview | null;
  apiConnected: boolean;
  errorMessage: string | null;
  isStale: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const query = new URLSearchParams({ scope });
    if (section) query.set("section", section);
    if (section && offset > 0) query.set("offset", String(offset));
    const response = await fetch(`${apiBaseUrl}/api/v1/dispositions/desk?${query.toString()}`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    const desk = (await response.json()) as DispositionDeskOverview;
    const generatedAt = new Date(desk.source_health.generated_at);
    return {
      desk,
      apiConnected: true,
      errorMessage: null,
      isStale: Number.isNaN(generatedAt.getTime()) || Date.now() - generatedAt.getTime() > 5 * 60 * 1000,
    };
  } catch (error) {
    return {
      desk: null,
      apiConnected: false,
      errorMessage: error instanceof Error ? error.message : "Disposition desk request failed.",
      isStale: false,
    };
  }
}

function dispositionIntelligenceTimestamp(value: string, boundary: "start" | "end") {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return boundary === "start"
    ? `${value}T00:00:00Z`
    : `${value}T23:59:59.999Z`;
}

export async function getDispositionIntelligence(
  filters: DispositionIntelligenceQuery = {},
): Promise<{
  intelligence: DispositionIntelligenceResponse | null;
  apiConnected: boolean;
  errorMessage: string | null;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const query = new URLSearchParams();
    const scalarKeys: Array<keyof Omit<DispositionIntelligenceQuery, "start_at" | "end_at">> = [
      "deal_id",
      "buyer_id",
      "agent_user_id",
      "source",
      "market",
      "asset_class",
    ];
    for (const key of scalarKeys) {
      const value = filters[key]?.trim();
      if (value) query.set(key, value);
    }
    if (filters.start_at?.trim()) {
      query.set("start_at", dispositionIntelligenceTimestamp(filters.start_at.trim(), "start"));
    }
    if (filters.end_at?.trim()) {
      query.set("end_at", dispositionIntelligenceTimestamp(filters.end_at.trim(), "end"));
    }
    const suffix = query.size ? `?${query.toString()}` : "";
    const response = await fetch(`${apiBaseUrl}/api/v1/dispositions/intelligence${suffix}`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      intelligence: (await response.json()) as DispositionIntelligenceResponse,
      apiConnected: true,
      errorMessage: null,
    };
  } catch (error) {
    return {
      intelligence: null,
      apiConnected: false,
      errorMessage: error instanceof Error ? error.message : "Disposition intelligence request failed.",
    };
  }
}

export async function getIntegrationStatuses(): Promise<{
  integrations: IntegrationStatus[];
  apiConnected: boolean;
}> {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/integrations/status`, {
      headers: await getServerApiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) throw await apiError(response);
    return {
      integrations: ((await response.json()) as { items: IntegrationStatus[] }).items,
      apiConnected: true,
    };
  } catch {
    return { integrations: [], apiConnected: false };
  }
}
