export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type RunView = {
  run_id: string;
  tenant_id: string;
  scenario_id: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type IncidentView = {
  incident_id: string;
  tenant_id: string;
  run_id: string;
  site_id: string;
  reported_device_id: string;
  symptom: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type EvidenceView = {
  evidence_id: string;
  tenant_id: string;
  run_id: string;
  source_type: string;
  captured_at: string;
  entity_ids: string[];
  payload: Record<string, JsonValue>;
  facts: string[];
  expires_at: string | null;
};

export type ProposalView = {
  proposal_id: string;
  tenant_id: string;
  run_id: string;
  incident_id: string;
  device_id: string;
  diagnosis: string;
  action_type: string;
  evidence_ids: string[];
  rationale: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ApprovalView = {
  approval_id: string;
  tenant_id: string;
  run_id: string;
  proposal_id: string;
  decision: string;
  decided_at: string;
  decided_by: string;
};

export type ExecutedActionView = {
  action_id: string;
  tenant_id: string;
  run_id: string;
  proposal_id: string;
  incident_id: string;
  device_id: string;
  action_type: string;
  executed_at: string;
};

export type FieldServiceWorkOrderView = {
  work_order_id: string;
  tenant_id: string;
  run_id: string;
  proposal_id: string;
  incident_id: string;
  device_id: string;
  site_id: string;
  attachment_id: string;
  switch_id: string;
  port_id: string;
  created_at: string;
};

export type RunStateResponse = {
  run: RunView;
  incidents: IncidentView[];
  evidence: EvidenceView[];
  proposals: ProposalView[];
  approvals: ApprovalView[];
  executed_actions: ExecutedActionView[];
  work_orders: FieldServiceWorkOrderView[];
  latest_event_seq: number;
};

export type ServiceIncidentView = {
  incident_id: string;
  tenant_id: string;
  run_id: string;
  site_id: string;
  service_key: string;
  symptom_key: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type OperationalSignalView = {
  signal_id: string;
  tenant_id: string;
  run_id: string;
  source: string;
  site_id: string;
  service_key: string;
  symptom_key: string;
  source_ref: string;
  received_at: string;
  safe_payload: Record<string, JsonValue>;
  incident_id: string | null;
};

export type MajorIncidentProposalView = {
  proposal_id: string;
  tenant_id: string;
  run_id: string;
  correlation_key: string;
  service_key: string;
  affected_site_ids: string[];
  dependency_id: string;
  dependency_name: string;
  action_type: string;
  evidence_ids: string[];
  summary: string;
  rationale: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type MajorIncidentApprovalView = {
  approval_id: string;
  tenant_id: string;
  run_id: string;
  proposal_id: string;
  decision: string;
  decided_at: string;
  decided_by: string;
};

export type MajorIncidentExecutionView = {
  execution_id: string;
  tenant_id: string;
  run_id: string;
  proposal_id: string;
  action_type: string;
  major_incident_id: string;
  executed_at: string;
};

export type MajorIncidentView = {
  major_incident_id: string;
  tenant_id: string;
  run_id: string;
  proposal_id: string;
  correlation_key: string;
  service_key: string;
  affected_site_ids: string[];
  dependency_id: string;
  dependency_name: string;
  summary: string;
  status: string;
  created_at: string;
};

export type Scenario2IngestionStateResponse = {
  run: RunView;
  service_incidents: ServiceIncidentView[];
  operational_signals: OperationalSignalView[];
  evidence: EvidenceView[];
  major_incident_proposals: MajorIncidentProposalView[];
  major_incident_approvals: MajorIncidentApprovalView[];
  major_incident_executions: MajorIncidentExecutionView[];
  major_incidents: MajorIncidentView[];
  latest_event_seq: number;
};

export type Scenario2SimulatorStepResponse = {
  state: Scenario2IngestionStateResponse;
  ingested: {
    signal: OperationalSignalView;
    service_incident: ServiceIncidentView;
    evidence_id: string;
    replayed: boolean;
    event_seq: number | null;
    dispatch_queued: boolean;
  } | null;
  complete: boolean;
  next_index: number;
};

export type Scenario2ApprovalDecisionResponse = {
  approval: MajorIncidentApprovalView;
  proposal: MajorIncidentProposalView;
  execution: MajorIncidentExecutionView | null;
  major_incident: MajorIncidentView | null;
  replayed: boolean;
};

export type ApplicationEventView = {
  event_id: string;
  tenant_id: string;
  run_id: string;
  seq: number;
  event_type: string;
  occurred_at: string;
  payload: Record<string, JsonValue>;
};

export type TimelineResponse = {
  run_id: string;
  events: ApplicationEventView[];
  next_cursor: number;
};

export type ApprovalDecisionResponse = {
  approval: ApprovalView;
  proposal: ProposalView;
  incident: IncidentView;
  executed_action: ExecutedActionView | null;
  work_order: FieldServiceWorkOrderView | null;
  replayed: boolean;
};

export type ApiErrorResponse = {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    details: Record<string, string>;
  };
};

export type HealthResponse = {
  status: string;
  phase: number;
  checkpoint: string;
  database_configured: boolean;
  database_reachable: boolean;
  adk_wired: boolean;
  adk_session_persistence_wired: boolean;
  adk_resumability_wired: boolean;
  gemini_configured: boolean;
  adk_model: string | null;
  sse_wired: boolean;
  automatic_dispatch_wired: boolean;
  scenario3_phase8c1_provider_reads_wired: boolean;
  scenario3_phase8c2_native_wired: boolean;
};

export type ConnectionState =
  | "Live"
  | "Reconnecting"
  | "Offline/Unavailable";
