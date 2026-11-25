export interface User {
  id: string
  email: string
  display_name: string
  role: 'ADMIN' | 'SUPERVISOR' | 'INVESTIGATOR' | 'ANALYST'
  is_active: boolean
  created_at: string
}

export interface Case {
  id: string
  case_code: string
  title: string
  case_type: string
  description?: string
  status: 'DRAFT' | 'ACTIVE' | 'ON_HOLD' | 'CLOSED'
  created_by?: string
  created_at: string
  updated_at: string
  members: { user_id: string; case_role: string }[]
}

export interface EvidenceItem {
  id: string
  case_id: string
  evidence_code: string
  original_filename: string
  sanitized_filename: string
  file_extension?: string
  mime_type?: string
  file_size_bytes?: number
  source_label?: string
  description?: string
  extracted_text?: string | null
  sha256_hash: string
  hash_algorithm: string
  integrity_status: 'UNVERIFIED' | 'VERIFIED' | 'MISMATCH' | 'VERIFICATION_FAILED'
  uploaded_by?: string
  uploaded_at: string
  parsing_status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'PARTIALLY_COMPLETED' | 'FAILED' | 'CANCELLED'
  processing_status?: string
  parsing_error?: string
  is_original: boolean
  version_number?: number
  supersedes_evidence_id?: string | null
  lifecycle_status?: 'ACTIVE' | 'SUPERSEDED' | 'WITHDRAWN'
  withdrawn_reason?: string | null
}

export interface ParsedRecord {
  id: string
  record_type: 'CDR' | 'TRANSACTION'
  source_row_number: number
  raw_record: Record<string, unknown>
  normalized_record: Record<string, unknown>
  parse_status: 'VALID' | 'INVALID' | 'SKIPPED'
  parse_error?: string
}

export interface AuditEvent {
  id: string
  event_type: string
  event_timestamp: string
  actor_user_id?: string
  evidence_id?: string
  event_metadata: Record<string, unknown>
  event_hash?: string
  previous_event_hash?: string
}

export interface GraphNode {
  id: string
  labels?: string[]
  normalized_number?: string
  normalized_identifier?: string
  case_id?: string
  [key: string]: unknown
}

export interface GraphEdge {
  id: string
  relationship_type?: string
  case_id?: string
  evidence_id?: string
  source_file_name?: string
  source_row_number?: number
  event_timestamp_utc?: string
  amount?: number
  currency?: string
  [key: string]: unknown
}

export interface ToastMessage {
  id: string
  message: string
  type: 'info' | 'warn' | 'error'
}

// ─── Intelligence Integration Layer (Phase 5A / 5B) ──────────────────────────
export type PriorityTier = 'HIGH' | 'REVIEW' | 'LOW'

export interface StructuredEvidenceRecord {
  reason: string
  evidence_type: string
  case_id?: string | null
  record_id?: string | null
  source_file?: string | null
  source_row?: number | null
  timestamp?: string | null
}

export interface InvestigationLead {
  lead_id: string
  source_entity: string
  target_entity: string
  source_case_ids: string[]
  target_case_ids: string[]
  is_cross_case: boolean
  confidence: number
  priority: PriorityTier
  prediction_type: 'Potential Association' | 'Candidate Link'
  evidence_strength: 'STRONG' | 'MODERATE' | 'WEAK'
  explanation: string
  supporting_modalities: string[]
  common_intermediates_count: number
  common_intermediates: string[]
  caveats: string[]
  supporting_records: StructuredEvidenceRecord[]
  conflicting_records?: StructuredEvidenceRecord[]
  status?: string
  model_version?: string
  reviewed_by?: string | null
  decision_rationale?: string | null
  created_at: string
}

export interface LeadResponse {
  total: number
  limit: number
  offset: number
  leads: InvestigationLead[]
}

export interface CrossCaseLeadSummary {
  lead_id: string
  source_entity: string
  target_entity: string
  source_cases: string[]
  target_cases: string[]
  confidence: number
  priority: PriorityTier
  supporting_modalities: string[]
  common_intermediates_count: number
  caveats: string[]
}

export interface CrossCaseResponse {
  total: number
  cross_case_leads: CrossCaseLeadSummary[]
}

export interface IdentityHypothesis {
  id: string
  hypothesis_key: string
  person_a_ref: string
  person_b_ref: string
  person_a_name: string
  person_b_name: string
  case_a_id?: string | null
  case_b_id?: string | null
  case_a_ref: string
  case_b_ref: string
  match_probability: number
  confidence_tier: string
  model_version: string
  supporting_evidence: string[]
  conflicting_evidence: string[]
  blocking_reasons: string[]
  status: string
  reviewed_by?: string | null
  reviewed_at?: string | null
  decision_rationale?: string | null
  created_at: string
  updated_at: string
  profile_a?: Record<string, unknown>
  profile_b?: Record<string, unknown>
  feature_explanation?: Record<string, number>
  decisions?: {
    id: string
    previous_status: string
    new_status: string
    reviewer_id?: string | null
    rationale: string
    created_at: string
  }[]
}

export interface EntityProfile {
  entity_id: string
  identifiers: string[]
  associated_cases: { case_id: string; case_code: string }[]
  phones: string[]
  devices: string[]
  vehicles: string[]
  locations: string[]
  communications: Record<string, unknown>[]
  financial_associations: Record<string, unknown>[]
  travel_observations: Record<string, unknown>[]
  evidence_references: {
    record_id: string
    record_type: string
    case_id: string
    case_code: string
    evidence_id: string
    evidence_code: string
    source_file: string
    source_row: number
    normalized_record: Record<string, unknown>
  }[]
  timeline: {
    timestamp: string
    modality: string
    case_code: string
    detail: Record<string, unknown>
  }[]
  identity_hypotheses: IdentityHypothesis[]
  priority_summary?: Record<string, unknown> | null
  disclaimer: string
}

export interface TimelineEvent {
  id: string
  timestamp: string
  modality: string
  participants: string[]
  summary: Record<string, unknown>
  provenance: {
    case_id: string
    case_code: string
    evidence_id: string
    evidence_code: string
    source_file: string
    source_row: number
    sha256_hash: string
  }
}

export interface StructuredClaim {
  claim_id: string
  case_id: string
  raw_text: string
  subject_person_id?: string | null
  subject_name?: string | null
  predicate: string
  object_entity_id?: string | null
  location_id?: string | null
  time_start?: string | null
  time_end?: string | null
  negated: boolean
  claim_confidence?: number
}

export interface ConsistencyResult {
  result_id: string
  claim: StructuredClaim
  status: string
  confidence: {
    statement_specificity: number
    evidence_coverage: number
    corroboration_strength: number
    contradiction_strength: number
    ambiguity_penalty: number
    overall_confidence: number
    label?: string
  }
  matched_evidence: StructuredEvidenceRecord[]
  conflicting_evidence: StructuredEvidenceRecord[]
  explanation: string
  caveats: string[]
  recommended_action: string
  evaluated_at: string
}

export interface DecisionHistoryItem {
  id: string
  category: 'IDENTITY_HYPOTHESIS' | 'INVESTIGATION_LEAD' | 'ANALYST_NOTE'
  target_id: string
  summary: string
  rationale: string
  reviewer_id?: string | null
  cases: string[]
  created_at: string
}

export interface ModelRegistryItem {
  id?: string
  model_name: string
  version: string
  feature_schema_version: string
  artifact_uri: string
  training_snapshot_id?: string
  evaluation_report?: Record<string, unknown>
  is_active: boolean
  created_at?: string
}

export interface AuditChainVerification {
  case_id: string
  total_events: number
  is_valid: boolean
  broken_event_id?: string | null
  reason?: string | null
}
