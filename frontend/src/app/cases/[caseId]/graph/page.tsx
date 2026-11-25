'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import dynamic from 'next/dynamic'
import AppShell from '@/components/layout/AppShell'
import GraphFilters from '@/components/graph/GraphFilters'
import NodeInspector from '@/components/graph/NodeInspector'
import EdgeInspector from '@/components/graph/EdgeInspector'
import { useToast } from '@/components/ui/ToastNotification'
import { graphApi, casesApi, intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { GraphNode, GraphEdge, Case, InvestigationLead } from '@/types'

// Load Cytoscape client-side only — stable dynamic import
const CytoscapeCanvas = dynamic(
  () => import('@/components/graph/CytoscapeCanvas'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full text-slate-400 text-xs gap-2">
        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Loading graph engine…
      </div>
    ),
  }
)

const VIEW_TABS = [
  { key: 'network',       label: 'Network' },
  { key: 'financial',     label: 'Financial' },
  { key: 'communication', label: 'Communication' },
  { key: 'location',      label: 'Location' },
  { key: 'timeline',      label: 'Timeline' },
]

interface EdgeDetail {
  edge_id: string
  relationship_type: string
  source: { labels: string[]; normalized_number?: string; normalized_identifier?: string }
  target: { labels: string[]; normalized_number?: string; normalized_identifier?: string }
  event?: {
    timestamp_utc?: string; duration_seconds?: number
    amount?: number; currency?: string; transaction_id?: string; transaction_type?: string
  }
  provenance?: {
    evidence_id?: string; source_file_name?: string; source_row_number?: number
    source_hash?: string; verification_status?: string; relationship_status?: string; confidence_label?: string
  }
  limitations?: string[]
  is_candidate?: boolean
  candidate_lead?: InvestigationLead
}

export default function GraphPage() {
  const router  = useRouter()
  const { caseId } = useParams<{ caseId: string }>()
  const { toast }  = useToast()

  // ── Graph data lives in refs → canvas never re-initialises on inspector open ──
  const nodesRef = useRef<GraphNode[]>([])
  const edgesRef = useRef<GraphEdge[]>([])
  const confirmedNodesRef = useRef<GraphNode[]>([])
  const confirmedEdgesRef = useRef<GraphEdge[]>([])
  const candidateLeadsRef = useRef<InvestigationLead[]>([])

  // ── UI state (none of these should re-trigger CytoscapeCanvas) ──────────────
  const [caseData, setCaseData]         = useState<Case | null>(null)
  const [graphKey, setGraphKey]         = useState(0)      // increment to force canvas rebuild
  const [graphStats, setGraphStats]     = useState({ nodes: 0, edges: 0 })
  const [loading, setLoading]           = useState(true)
  const [viewTab, setViewTab]           = useState('network')
  const [leftOpen, setLeftOpen]         = useState(true)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<EdgeDetail | null>(null)
  const [showCandidateLinks, setShowCandidateLinks] = useState(true)
  const [candidateCount, setCandidateCount] = useState(0)
  const [snapshotTag, setSnapshotTag] = useState<string>('Live')
  const [pathFrom, setPathFrom] = useState('')
  const [pathTo, setPathTo] = useState('')
  const [pathResult, setPathResult] = useState<string | null>(null)

  // ── Filter state ─────────────────────────────────────────────────────────────
  const [entitySearch, setEntitySearch] = useState('')
  const [depth, setDepth]               = useState(2)
  const [relTypes, setRelTypes]         = useState<string[]>([
    'CALLED', 'TRANSFERRED_TO', 'USED_DEVICE', 'CONNECTED_TO_TOWER',
  ])

  // ── Helper to assemble visible elements ───────────────────────────────────────
  const rebuildVisibleGraph = useCallback((
    includeCandidates: boolean,
    baseNodes = confirmedNodesRef.current,
    baseEdges = confirmedEdgesRef.current,
    leads = candidateLeadsRef.current,
    activeTab = viewTab,
  ) => {
    const tabAllowedRels: Record<string, string[] | null> = {
      network: null,
      financial: ['TRANSFERRED_TO', 'OWNED_ACCOUNT'],
      communication: ['CALLED', 'MESSAGED', 'USED_PHONE', 'USED_DEVICE'],
      location: ['CONNECTED_TO_TOWER', 'SIGHTED_AT', 'TRAVELED_TO', 'VISITED'],
      timeline: null,
    }
    const allowed = tabAllowedRels[activeTab] ?? null
    const filteredBaseEdges = allowed
      ? baseEdges.filter((e) => allowed.includes(String((e as Record<string, unknown>).relationship_type ?? '')))
      : baseEdges

    let filteredBaseNodes = baseNodes
    if (allowed) {
      const keptIds = new Set<string>()
      for (const e of filteredBaseEdges) {
        const raw = e as Record<string, unknown>
        if (raw.source) keptIds.add(String(raw.source))
        if (raw.target) keptIds.add(String(raw.target))
      }
      filteredBaseNodes = baseNodes.filter((n) => keptIds.has(String(n.id)))
    }

    if (!includeCandidates || leads.length === 0) {
      nodesRef.current = [...filteredBaseNodes]
      edgesRef.current = [...filteredBaseEdges]
    } else {
      const existingNodeIds = new Set(filteredBaseNodes.map((n) => String(n.id)))
      const additionalNodes: GraphNode[] = []
      for (const lead of leads) {
        if (!existingNodeIds.has(lead.source_entity)) {
          additionalNodes.push({
            id: lead.source_entity,
            labels: ['Person'],
            normalized_identifier: lead.source_entity,
          })
          existingNodeIds.add(lead.source_entity)
        }
        if (!existingNodeIds.has(lead.target_entity)) {
          additionalNodes.push({
            id: lead.target_entity,
            labels: ['Person'],
            normalized_identifier: lead.target_entity,
          })
          existingNodeIds.add(lead.target_entity)
        }
      }

      const candidateEdges: GraphEdge[] = leads.map((lead) => ({
        id: `lead_${lead.lead_id}`,
        source: lead.source_entity,
        target: lead.target_entity,
        relationship_type: lead.prediction_type,
        is_candidate: true,
        candidate_lead: lead,
      } as unknown as GraphEdge))

      nodesRef.current = [...filteredBaseNodes, ...additionalNodes]
      edgesRef.current = [...filteredBaseEdges, ...candidateEdges]
    }
    setGraphStats({ nodes: nodesRef.current.length, edges: edgesRef.current.length })
    setGraphKey((k) => k + 1)
  }, [viewTab])

  // ── Load graph data — only updates refs, then bumps graphKey to rebuild canvas ─
  const loadGraph = useCallback(async (params?: Record<string, unknown>, caseCodeOverride?: string) => {
    setLoading(true)
    setSelectedNode(null)
    setSelectedEdge(null)
    try {
      let baseNodes: GraphNode[] = []
      let baseEdges: GraphEdge[] = []
      try {
        const { data } = await graphApi.subgraph(caseId, {
          depth,
          relationship_types: relTypes.join(','),
          entity: entitySearch || undefined,
          limit_nodes: 200,
          ...params,
        })
        baseNodes = data.nodes ?? []
        baseEdges = data.edges ?? []
        graphApi.snapshot(caseId)
          .then(({ data: snap }) => {
            if (snap?.active_snapshot?.version_tag) setSnapshotTag(snap.active_snapshot.version_tag)
          })
          .catch(() => {})
      } catch {
        // Base graph may be empty if evidence not yet imported
      }
      confirmedNodesRef.current = baseNodes
      confirmedEdgesRef.current = baseEdges

      // Fetch AI Candidate Leads
      let leads: InvestigationLead[] = []
      const effectiveCaseCode = caseCodeOverride || caseData?.case_code || caseId
      try {
        const { data: leadData } = await intelligenceApi.getLeads({
          case_id: effectiveCaseCode,
          limit: 100,
        })
        leads = leadData.leads ?? []
        if (leads.length === 0 && effectiveCaseCode !== caseId) {
          const fallbackRes = await intelligenceApi.getLeads({ case_id: caseId, limit: 100 })
          leads = fallbackRes.data.leads ?? []
        }
      } catch {
        // Leads optional
      }
      candidateLeadsRef.current = leads
      setCandidateCount(leads.length)

      rebuildVisibleGraph(showCandidateLinks, baseNodes, baseEdges, leads)
    } catch {
      toast('Failed to load graph', 'error')
      nodesRef.current = []
      edgesRef.current = []
      setGraphStats({ nodes: 0, edges: 0 })
      setGraphKey((k) => k + 1)
    } finally {
      setLoading(false)
    }
  }, [caseId, caseData, depth, relTypes, entitySearch, showCandidateLinks, rebuildVisibleGraph, toast])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    let activeCaseCode = caseId
    casesApi.get(caseId)
      .then(({ data }) => {
        setCaseData(data)
        if (data?.case_code) {
          activeCaseCode = data.case_code
        }
      })
      .catch(() => {})
      .finally(() => {
        loadGraph(undefined, activeCaseCode)
      })
  }, [caseId, router]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleCandidateLinks = useCallback(() => {
    setShowCandidateLinks((prev) => {
      const next = !prev
      rebuildVisibleGraph(next)
      return next
    })
  }, [rebuildVisibleGraph])

  // ── Node click — only sets inspector state, never touches graph data ─────────
  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node)
    setSelectedEdge(null)
  }, [])

  // ── Edge click — handles candidate links & confirmed edges ──────────────────
  const handleEdgeClick = useCallback(async (edgeId: string) => {
    const localEdge = edgesRef.current.find((e) => (e as Record<string, unknown>).id === edgeId)
    const raw = localEdge as Record<string, unknown> | undefined

    if (raw?.is_candidate && raw.candidate_lead) {
      const lead = raw.candidate_lead as InvestigationLead
      setSelectedEdge({
        edge_id: edgeId,
        relationship_type: lead.prediction_type,
        source: { labels: ['Person'], normalized_identifier: lead.source_entity },
        target: { labels: ['Person'], normalized_identifier: lead.target_entity },
        is_candidate: true,
        candidate_lead: lead,
      })
      setSelectedNode(null)
      return
    }

    if (localEdge) {
      // Build edge detail from local data — no API call needed
      const allNodes = nodesRef.current
      const nodeMap  = Object.fromEntries(allNodes.map((n) => [n.id, n]))
      const src = nodeMap[(localEdge as Record<string,unknown>).source as string] ?? {}
      const tgt = nodeMap[(localEdge as Record<string,unknown>).target as string] ?? {}
      const e   = localEdge as Record<string, unknown>

      setSelectedEdge({
        edge_id: edgeId,
        relationship_type: (e.relationship_type as string) ?? '',
        source: { labels: (src as GraphNode).labels as string[] ?? [], normalized_number: (src as GraphNode).normalized_number, normalized_identifier: (src as GraphNode).normalized_identifier },
        target: { labels: (tgt as GraphNode).labels as string[] ?? [], normalized_number: (tgt as GraphNode).normalized_number, normalized_identifier: (tgt as GraphNode).normalized_identifier },
        event: {
          timestamp_utc:    e.event_timestamp_utc as string,
          duration_seconds: e.duration_seconds as number,
          amount:           e.amount as number,
          currency:         e.currency as string,
          transaction_id:   e.transaction_id as string,
          transaction_type: e.transaction_type as string,
        },
        provenance: {
          evidence_id:         e.evidence_id as string,
          source_file_name:    e.source_file_name as string,
          source_row_number:   e.source_row_number as number,
          source_hash:         e.source_hash as string,
          verification_status: e.verification_status as string,
          confidence_label:    e.confidence_label as string,
        },
        limitations: [
          'This record indicates a communication or financial event between identifiers.',
          'It does not establish who physically used the phone or account.',
          'A graph path represents recorded relationships — not proof of criminal conduct.',
        ],
      })
      setSelectedNode(null)
      return
    }

    // Fallback — try API
    try {
      const { data } = await graphApi.getEdge(caseId, edgeId)
      setSelectedEdge(data)
      setSelectedNode(null)
    } catch {
      toast('Could not load edge details', 'warn')
    }
  }, [caseId, toast])

  const closeInspector = useCallback(() => {
    setSelectedNode(null)
    setSelectedEdge(null)
  }, [])

  const isEmpty = graphStats.nodes === 0 && !loading

  return (
    <AppShell>
      <div className="flex flex-col h-[calc(100vh-56px)] bg-brand-bg overflow-hidden">

        {/* Sub-header */}
        <div className="bg-[#091420] border-b border-brand-border px-4 py-2 flex flex-wrap items-center justify-between gap-2.5 shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold text-white">Knowledge Graph</h1>
              {caseData && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-brand-cyan/10 text-brand-cyan border border-brand-cyan/30">
                  {caseData.case_code}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {caseData?.title ?? 'Loading…'} · {graphStats.nodes} nodes, {graphStats.edges} edges
            </p>
          </div>

          {/* Controls: View tabs & AI Candidate Leads Toggle */}
          <div className="flex items-center gap-2">
            <button
              onClick={toggleCandidateLinks}
              className={`px-2.5 py-1 rounded-md text-xs font-mono font-medium transition flex items-center gap-1.5 border ${
                showCandidateLinks
                  ? 'bg-purple-500/20 text-purple-300 border-purple-500/40 shadow-sm'
                  : 'bg-[#07111A] text-slate-400 border-brand-border hover:text-slate-200'
              }`}
              title="Toggle AI GraphSAGE candidate associations"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${showCandidateLinks ? 'bg-purple-400 animate-pulse' : 'bg-slate-500'}`} />
              <span>AI Leads</span>
              {candidateCount > 0 && (
                <span className="px-1.5 py-0.2 text-[10px] rounded bg-purple-500/30 text-purple-200 font-bold">
                  {candidateCount}
                </span>
              )}
            </button>

            <div className="flex items-center space-x-1 bg-[#07111A] p-0.5 rounded-lg border border-brand-border text-xs font-medium">
              {VIEW_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => {
                    setViewTab(t.key)
                    rebuildVisibleGraph(showCandidateLinks, confirmedNodesRef.current, confirmedEdgesRef.current, candidateLeadsRef.current, t.key)
                  }}
                  className={`px-2.5 py-1 rounded-md transition ${
                    viewTab === t.key
                      ? 'text-black bg-brand-cyan font-semibold shadow-sm'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/80'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Three-column workspace */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left control rail */}
          <aside className={`${leftOpen ? 'w-60' : 'w-10'} bg-brand-panel border-r border-brand-border flex flex-col shrink-0 z-20 transition-all duration-300 overflow-hidden`}>
            <button
              onClick={() => setLeftOpen((v) => !v)}
              className="p-2 text-slate-400 hover:text-white self-end"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {leftOpen
                  ? <path d="M15 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                  : <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />}
              </svg>
            </button>
            {leftOpen && (
              <>
                <div className="flex-1 overflow-y-auto">
                  <GraphFilters
                    entitySearch={entitySearch}
                    onEntitySearchChange={setEntitySearch}
                    depth={depth}
                    onDepthChange={setDepth}
                    relationshipTypes={relTypes}
                    onRelationshipTypesChange={setRelTypes}
                    onApply={() => loadGraph()}
                  />
                  {/* Path Finder */}
                  <div className="px-3 pb-3 pt-2 border-t border-brand-border/50 space-y-2 text-xs">
                    <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                      Path Finder
                    </label>
                    <input
                      value={pathFrom}
                      onChange={(e) => setPathFrom(e.target.value)}
                      placeholder="Source entity ID"
                      className="w-full bg-[#070D14] border border-brand-border rounded px-2 py-1 text-[11px] text-slate-200"
                    />
                    <input
                      value={pathTo}
                      onChange={(e) => setPathTo(e.target.value)}
                      placeholder="Target entity ID"
                      className="w-full bg-[#070D14] border border-brand-border rounded px-2 py-1 text-[11px] text-slate-200"
                    />
                    <button
                      onClick={async () => {
                        if (!pathFrom.trim() || !pathTo.trim()) return
                        try {
                          const { data } = await graphApi.findPath(caseId, pathFrom.trim(), pathTo.trim())
                          setPathResult(
                            data?.found
                              ? `Found (${data.hops} hops): ${(data.path || []).join(' → ')}`
                              : 'No path found within 4 hops'
                          )
                        } catch {
                          setPathResult('Path query unavailable')
                        }
                      }}
                      className="w-full py-1.5 bg-brand-surface hover:bg-brand-panel border border-brand-border text-brand-cyan text-[11px] rounded font-medium"
                    >
                      Trace Shortest Path
                    </button>
                    {pathResult && (
                      <div className="p-2 rounded bg-[#070D14] border border-brand-border text-[10px] font-mono text-slate-300 break-words">
                        {pathResult}
                      </div>
                    )}
                  </div>
                </div>
                <div className="p-2.5 border-t border-brand-border/80 bg-brand-bg/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-brand-green animate-pulse" />
                    Snapshot
                  </span>
                  <span className="text-brand-cyan truncate max-w-[110px]" title={snapshotTag}>{snapshotTag}</span>
                </div>
              </>
            )}
          </aside>

          {/* Canvas */}
          <section className="flex-1 relative bg-brand-bg canvas-bg-grid overflow-hidden">

            {/* Refresh button */}
            <div className="absolute top-4 left-4 z-30 flex items-center space-x-1 bg-brand-panel/90 backdrop-blur border border-brand-border/80 rounded-lg p-1 shadow-2xl">
              <button
                onClick={() => loadGraph()}
                className="px-2.5 h-7 text-[11px] font-mono text-slate-300 hover:text-white hover:bg-slate-700/70 rounded transition"
                title="Refresh"
              >
                ↺
              </button>
            </div>

            {/* Evidence disclaimer */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 bg-brand-panel/90 backdrop-blur border border-brand-amber/30 px-4 py-2 rounded-full text-[10px] text-slate-400 font-mono text-center max-w-xl pointer-events-none">
              ⚠ Displayed relationships are evidence-derived records. They do not establish identity, intent, or criminal conduct.
            </div>

            {loading ? (
              <div className="flex items-center justify-center h-full text-slate-400 text-xs gap-2">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Building graph…
              </div>
            ) : isEmpty ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
                <svg className="w-12 h-12 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                </svg>
                <p className="text-sm">No graph data yet.</p>
                <p className="text-xs text-slate-500">Import and parse evidence to build the knowledge graph.</p>
              </div>
            ) : (
              // key={graphKey} ensures canvas only re-mounts when we explicitly
              // reload data — NOT when inspector state changes
              <CytoscapeCanvas
                key={graphKey}
                nodes={nodesRef.current}
                edges={edgesRef.current}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
              />
            )}

            {/* Node inspector — rendered on top of canvas, no canvas re-mount */}
            {selectedNode && (
              <NodeInspector node={selectedNode} onClose={closeInspector} />
            )}

            {/* Edge inspector */}
            {selectedEdge && !selectedNode && (
              <EdgeInspector edge={selectedEdge} onClose={closeInspector} />
            )}
          </section>
        </div>
      </div>
    </AppShell>
  )
}
