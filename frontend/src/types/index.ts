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
  sha256_hash: string
  hash_algorithm: string
  integrity_status: 'UNVERIFIED' | 'VERIFIED' | 'MISMATCH' | 'VERIFICATION_FAILED'
  uploaded_by?: string
  uploaded_at: string
  parsing_status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'PARTIALLY_COMPLETED' | 'FAILED'
  parsing_error?: string
  is_original: boolean
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
