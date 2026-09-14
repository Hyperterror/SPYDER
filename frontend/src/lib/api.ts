import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

// ── Request interceptor: inject JWT ──────────────────────────────────────
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers = config.headers ?? {}
      config.headers['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})

// ── Response interceptor: auto-refresh on 401 ────────────────────────────
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = typeof window !== 'undefined'
        ? localStorage.getItem('refresh_token')
        : null
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
            refresh_token: refresh,
          })
          localStorage.setItem('access_token', data.access_token)
          original.headers['Authorization'] = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          if (typeof window !== 'undefined') {
            localStorage.removeItem('access_token')
            localStorage.removeItem('refresh_token')
            window.location.href = '/login'
          }
        }
      } else {
        if (typeof window !== 'undefined') window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ─── Auth ─────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/api/v1/auth/login', { email, password }),
  refresh: (refreshToken: string) =>
    api.post('/api/v1/auth/refresh', { refresh_token: refreshToken }),
  logout: () => api.post('/api/v1/auth/logout'),
  me: () => api.get('/api/v1/auth/me'),
}

// ─── Cases ────────────────────────────────────────────────────────────────
export const casesApi = {
  list: () => api.get('/api/v1/cases'),
  create: (body: { title: string; case_type: string; description?: string }) =>
    api.post('/api/v1/cases', body),
  get: (caseId: string) => api.get(`/api/v1/cases/${caseId}`),
  update: (caseId: string, body: Record<string, unknown>) =>
    api.patch(`/api/v1/cases/${caseId}`, body),
  summary: (caseId: string) => api.get(`/api/v1/cases/${caseId}/summary`),
  addMember: (caseId: string, userId: string, role: string) =>
    api.post(`/api/v1/cases/${caseId}/members`, { user_id: userId, case_role: role }),
  removeMember: (caseId: string, userId: string) =>
    api.delete(`/api/v1/cases/${caseId}/members/${userId}`),
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
  verifyIntegrity: (caseId: string, evidenceId: string) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/verify-integrity`),
  parse: (caseId: string, evidenceId: string, columnMapping?: Record<string, string>) =>
    api.post(`/api/v1/cases/${caseId}/evidence/${evidenceId}/parse`, columnMapping ?? null),
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
  getNotes: (caseId: string) => api.get(`/api/v1/cases/${caseId}/notes`),
  createNote: (caseId: string, noteText: string, evidenceId?: string, graphRef?: object) =>
    api.post(`/api/v1/cases/${caseId}/notes`, {
      note_text: noteText,
      evidence_id: evidenceId,
      graph_reference: graphRef,
    }),
}

export default api
