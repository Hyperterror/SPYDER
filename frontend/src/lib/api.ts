import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import type {
  LeadResponse,
  InvestigationLead,
  StructuredEvidenceRecord,
  CrossCaseResponse,
  IdentityHypothesis,
  EntityProfile,
  ConsistencyResult,
  DecisionHistoryItem,
  ModelRegistryItem,
  TimelineEvent,
  AuditChainVerification,
} from '@/types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// Keep short-lived access token in memory (never store long-lived refresh tokens in localStorage)
let inMemoryAccessToken: string | null = null

export function setInMemoryAccessToken(token: string | null) {
  inMemoryAccessToken = token
  if (typeof window !== 'undefined') {
    if (token) {
      sessionStorage.setItem('access_token', token)
    } else {
      sessionStorage.removeItem('access_token')
    }
    // Remove legacy localStorage credentials if present
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }
}

export function getInMemoryAccessToken(): string | null {
  if (inMemoryAccessToken) return inMemoryAccessToken
  if (typeof window !== 'undefined') {
    const legacy = localStorage.getItem('access_token')
    if (legacy) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    }
    inMemoryAccessToken = sessionStorage.getItem('access_token')
    return inMemoryAccessToken
  }
  return null
}

function getCookieValue(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : null
}

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 30_000,
})

// ── Request interceptor: inject short-lived JWT ──────────────────────────
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getInMemoryAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor: auto-refresh via HttpOnly cookie + CSRF ────────
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && original && !original._retry && !String(original.url).includes('/auth/refresh')) {
      original._retry = true
      try {
        const csrf = getCookieValue('spyder_csrf_token')
        const { data } = await axios.post(
          `${BASE_URL}/api/v1/auth/refresh`,
          {},
          {
            withCredentials: true,
            headers: csrf ? { 'X-CSRF-Token': csrf } : {},
          }
        )
        setInMemoryAccessToken(data.access_token)
        original.headers['Authorization'] = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        setInMemoryAccessToken(null)
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('user')
          localStorage.removeItem('user')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

// ─── Auth ─────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/api/v1/auth/login', { email, password }),
  refresh: () => {
    const csrf = getCookieValue('spyder_csrf_token')
    return api.post('/api/v1/auth/refresh', {}, { headers: csrf ? { 'X-CSRF-Token': csrf } : {} })
  },
  logout: () => api.post('/api/v1/auth/logout'),
  me: () => api.get('/api/v1/auth/me'),
}

// ─── Cases ────────────────────────────────────────────────────────────────
export const casesApi = {
  list: () => api.get('/api/v1/cases'),
  create: (body: { title: string; case_type: string; description?: string; external_case_ref?: string }) =>
    api.post('/api/v1/cases', body),
  get: (caseId: string) => api.get(`/api/v1/cases/${caseId}`),
  update: (caseId: string, body: Record<string, unknown>) =>
    api.patch(`/api/v1/cases/${caseId}`, body),
  summary: (caseId: string) => api.get(`/api/v1/cases/${caseId}/summary`),
  addMember: (caseId: string, userId: string, role: string) =>
    api.post(`/api/v1/cases/${caseId}/members`, { user_id: userId, case_role: role }),
  removeMember: (caseId: string, userId: string) =>
    api.delete(`/api/v1/cases/${caseId}/members/${userId}`),
  timeline: (caseId: string, params?: { modality?: string; entity?: string; limit?: number }) =>
    api.get<{ case_id: string; case_code: string; total: number; events: TimelineEvent[] }>(
      `/api/v1/cases/${caseId}/timeline`,
      { params }
    ),
}

// ─── Evidence ─────────────────────────────────────────────────────────────
export const evidenceApi = {
  list: (caseId: string) => api.get(`/api/v1/cases/${caseId}/evidence`),
  upload: (caseId: string, formData: FormData) =>
    api.post(`/api/v1/cases/${caseId}/evidence/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  get: (caseId: string, evidenceId: string) =>
    api.get(`/api/v1/cases/${caseId}/evidence/${evidenceId}`),
  download: (caseId: string, evidenceId: string) =>
    api.get(`/api/v1/cases/${caseId}/evidence/${evidenceId}/download`, { responseType: 'blob' }),
  supersede: (caseId: string, evidenceId: string, formData: FormData) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/supersede`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  withdraw: (caseId: string, evidenceId: string, reason: string) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/withdraw`, { reason }),
  verifyIntegrity: (caseId: string, evidenceId: string) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/verify-integrity`),
  parse: (caseId: string, evidenceId: string, columnMapping?: Record<string, string>) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/parse`, columnMapping ?? null),
  process: (caseId: string, evidenceId: string, runSync = true) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/process`, null, {
      params: { run_sync: runSync },
    }),
  cancel: (caseId: string, evidenceId: string) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/cancel`),
  retry: (caseId: string, evidenceId: string, runSync = true) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/retry`, null, {
      params: { run_sync: runSync },
    }),
  status: (caseId: string, evidenceId: string) =>
    api.get(`/api/v1/cases/${caseId}/evidence/${evidenceId}/status`),
  parsedRecords: (caseId: string, evidenceId: string, offset = 0, limit = 100) =>
    api.get(`/api/v1/cases/${caseId}/evidence/${evidenceId}/parsed-records`, {
      params: { offset, limit },
    }),
  audit: (caseId: string, evidenceId: string) =>
    api.get(`/api/v1/cases/${caseId}/evidence/${evidenceId}/audit`),
}

// ─── Graph ────────────────────────────────────────────────────────────────
export const graphApi = {
  subgraph: (caseId: string, params?: Record<string, unknown>) =>
    api.get(`/api/v1/cases/${caseId}/graph/subgraph`, { params }),
  snapshot: (caseId: string) =>
    api.get(`/api/v1/cases/${caseId}/graph/snapshot`),
  entitySearch: (caseId: string, q: string) =>
    api.get(`/api/v1/cases/${caseId}/graph/entity-search`, { params: { q } }),
  getNode: (caseId: string, nodeId: string) =>
    api.get(`/api/v1/cases/${caseId}/graph/nodes/${nodeId}`),
  getEdge: (caseId: string, edgeId: string) =>
    api.get(`/api/v1/cases/${caseId}/graph/edges/${edgeId}`),
  findPath: (caseId: string, sourceEntity: string, targetEntity: string, maxDepth = 4) =>
    api.post(`/api/v1/cases/${caseId}/graph/path`, {
      source_entity: sourceEntity,
      target_entity: targetEntity,
      max_depth: maxDepth,
    }),
}

// ─── Audit & Notes ────────────────────────────────────────────────────────
export const auditApi = {
  getLog: (caseId: string, params?: Record<string, unknown>) =>
    api.get(`/api/v1/cases/${caseId}/audit`, { params }),
  verifyChain: (caseId: string) =>
    api.get<AuditChainVerification>(`/api/v1/cases/${caseId}/audit/verify`),
  getNotes: (caseId: string) => api.get(`/api/v1/cases/${caseId}/notes`),
  createNote: (caseId: string, noteText: string, evidenceId?: string, graphRef?: object) =>
    api.post(`/api/v1/cases/${caseId}/notes`, {
      note_text: noteText,
      evidence_id: evidenceId,
      graph_reference: graphRef,
    }),
}

// ─── Intelligence Integration Layer ──────────────────────────────────────
export const intelligenceApi = {
  getLeads: (params?: {
    case_id?: string
    min_confidence?: number
    priority?: string
    is_cross_case?: boolean
    status_filter?: string
    limit?: number
    offset?: number
  }) => api.get<LeadResponse>('/api/v1/intelligence/leads', { params }),

  getLead: (leadId: string) =>
    api.get<InvestigationLead>(`/api/v1/intelligence/leads/${leadId}`),

  getLeadEvidence: (leadId: string) =>
    api.get<StructuredEvidenceRecord[]>(`/api/v1/intelligence/leads/${leadId}/evidence`),

  reviewLead: (leadId: string, status: string, rationale: string) =>
    api.post(`/api/v1/intelligence/leads/${leadId}/review`, { status, rationale }),

  getCrossCase: (params?: {
    min_confidence?: number
    priority?: string
    limit?: number
    offset?: number
  }) => api.get<CrossCaseResponse>('/api/v1/intelligence/cross-case', { params }),

  listIdentityHypotheses: (params?: {
    status?: string
    min_probability?: number
    limit?: number
    offset?: number
  }) =>
    api.get<{ total: number; limit: number; offset: number; hypotheses: IdentityHypothesis[] }>(
      '/api/v1/intelligence/identity-hypotheses',
      { params }
    ),

  getIdentityHypothesis: (hypothesisId: string) =>
    api.get<IdentityHypothesis>(`/api/v1/intelligence/identity-hypotheses/${hypothesisId}`),

  reviewIdentityHypothesis: (hypothesisId: string, status: string, rationale: string) =>
    api.post<IdentityHypothesis>(`/api/v1/intelligence/identity-hypotheses/${hypothesisId}/review`, {
      status,
      rationale,
    }),

  getEntityProfile: (entityId: string) =>
    api.get<EntityProfile>(`/api/v1/intelligence/entities/${encodeURIComponent(entityId)}`),

  getPriorities: (params?: { case_id?: string; priority?: string; limit?: number; offset?: number }) =>
    api.get('/api/v1/intelligence/priorities', { params }),

  getPriorityById: (personId: string) =>
    api.get(`/api/v1/intelligence/priorities/${encodeURIComponent(personId)}`),

  analyzeStatement: (caseId: string, statementText: string, subjectPersonId?: string) =>
    api.post<{ results: ConsistencyResult[] }>('/api/v1/intelligence/consistency/analyze', {
      case_id: caseId,
      statement_text: statementText,
      subject_person_id: subjectPersonId || undefined,
    }),

  listConsistency: (params?: { case_id?: string; status?: string; limit?: number; offset?: number }) =>
    api.get<{ total: number; results: ConsistencyResult[] }>('/api/v1/intelligence/consistency', { params }),

  getConsistency: (resultId: string) =>
    api.get<ConsistencyResult>(`/api/v1/intelligence/consistency/${resultId}`),

  correctClaim: (
    resultId: string,
    payload: {
      predicate?: string
      object_entity_id?: string
      location_id?: string
      time_start?: string
      time_end?: string
      negated?: boolean
      reviewer_comment?: string
    }
  ) => api.patch(`/api/v1/intelligence/consistency/${resultId}/claim`, payload),

  reviewConsistency: (resultId: string, comment: string) =>
    api.post(`/api/v1/intelligence/consistency/${resultId}/review`, { comment }),

  listDecisions: (limit = 100) =>
    api.get<{ total: number; decisions: DecisionHistoryItem[] }>('/api/v1/intelligence/decisions', {
      params: { limit },
    }),

  listModels: () =>
    api.get<{ models: ModelRegistryItem[] }>('/api/v1/intelligence/models'),
}

export default api
