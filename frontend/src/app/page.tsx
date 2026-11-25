'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import KpiCard from '@/components/ui/KpiCard'
import StatusBadge from '@/components/ui/StatusBadge'
import ActionQueueItem from '@/components/ui/ActionQueueItem'
import Modal from '@/components/ui/Modal'
import { casesApi, evidenceApi, intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case, EvidenceItem, InvestigationLead } from '@/types'

/* ─── KPI Icons ─────────────────────────────────────────────────────────── */
const CasesIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
  </svg>
)
const ReviewsIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
  </svg>
)
const ContradictionsIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
  </svg>
)
const LinksIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
  </svg>
)

function caseStatusToVariant(status: string) {
  const m: Record<string, string> = {
    ACTIVE: 'in-progress',
    ON_HOLD: 'under-review',
    CLOSED: 'closed',
    DRAFT: 'draft',
  }
  return m[status] ?? 'active'
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function DashboardPage() {
  const router = useRouter()
  const [cases, setCases]                   = useState<Case[]>([])
  const [recentEvidence, setRecentEvidence] = useState<(EvidenceItem & { case_code?: string })[]>([])
  const [leads, setLeads]                   = useState<InvestigationLead[]>([])
  const [leadsTotal, setLeadsTotal]         = useState<number>(0)
  const [contradictionsTotal, setContradictionsTotal] = useState<number>(0)
  const [crossCaseTotal, setCrossCaseTotal] = useState<number>(0)
  const [loading, setLoading]               = useState(true)
  const [selectedCase, setSelected]         = useState<Case | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    casesApi.list()
      .then(async ({ data }) => {
        setCases(data)
        const evLists = await Promise.all(
          data.slice(0, 4).map(async (c: Case) => {
            try {
              const evRes = await evidenceApi.list(c.id)
              return (evRes.data as EvidenceItem[]).map((ev) => ({ ...ev, case_code: c.case_code }))
            } catch {
              return []
            }
          })
        )
        const flat = evLists.flat().sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at))
        setRecentEvidence(flat.slice(0, 6))
      })
      .catch(() => {})
      .finally(() => setLoading(false))

    intelligenceApi.getLeads({ limit: 4 })
      .then(({ data }) => {
        setLeads(data.leads ?? [])
        setLeadsTotal(data.total ?? 0)
      })
      .catch(() => {})

    intelligenceApi.getCrossCase({ limit: 1 })
      .then(({ data }) => {
        setCrossCaseTotal(data.total ?? 0)
      })
      .catch(() => {})

    intelligenceApi.listConsistency({ status: 'CONTRADICTED', limit: 1 })
      .then(({ data }) => {
        setContradictionsTotal(data.total ?? 0)
      })
      .catch(() => {})
  }, [router])

  const activeCases = cases.filter((c) => c.status === 'ACTIVE').length

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        {/* Page heading */}
        <section className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-brand-border/40 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Investigation Overview</h1>
            <p className="text-xs text-slate-400 mt-0.5">Your active investigations and review queue</p>
          </div>
          <div className="flex items-center space-x-2 text-[10px] font-mono tracking-widest text-slate-400 uppercase">
            <span className="hover:text-brand-cyan cursor-default">DATA</span>
            <span className="text-slate-600">|</span>
            <span className="hover:text-brand-cyan cursor-default">PEOPLE</span>
            <span className="text-slate-600">|</span>
            <span className="hover:text-brand-cyan cursor-default">PATTERNS</span>
            <span className="text-slate-600">|</span>
            <span className="text-brand-cyan font-semibold">JUSTICE</span>
          </div>
        </section>

        {/* KPI Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard icon={<CasesIcon />}         label="Active Cases"     value={activeCases}         trendDelta={cases.length} color="cyan"   />
          <KpiCard icon={<ReviewsIcon />}        label="Active Leads"     value={leadsTotal}          trendDelta={0}            color="red"    />
          <KpiCard icon={<ContradictionsIcon />} label="Contradictions"   value={contradictionsTotal} trendDelta={0}            color="amber"  />
          <KpiCard icon={<LinksIcon />}          label="Cross-Case Links" value={crossCaseTotal}      trendDelta={0}            color="purple" />
        </section>

        {/* Middle: Investigations + Priority Queue */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Active Investigations */}
          <div className="lg:col-span-7 bg-brand-panel border border-brand-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-white tracking-wide">Active Investigations</h2>
              <Link href="/cases" className="text-xs text-brand-cyan hover:underline flex items-center gap-1 font-medium">
                View All <span>→</span>
              </Link>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-10 text-slate-400 text-xs">
                <svg className="w-4 h-4 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading investigations…
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead>
                    <tr className="border-b border-brand-border text-[11px] font-mono uppercase text-slate-400">
                      <th className="pb-2.5 font-medium">Case ID</th>
                      <th className="pb-2.5 font-medium">Case Name</th>
                      <th className="pb-2.5 font-medium">Type</th>
                      <th className="pb-2.5 font-medium">Last Updated</th>
                      <th className="pb-2.5 font-medium">Status</th>
                      <th className="pb-2.5 font-medium text-right"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-brand-border/40">
                    {cases.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-slate-400">
                          No authorized cases found. <Link href="/cases" className="text-brand-cyan hover:underline">Create Case →</Link>
                        </td>
                      </tr>
                    ) : cases.map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => setSelected(c)}
                        className="hover:bg-brand-surface/70 cursor-pointer transition-colors group"
                      >
                        <td className="py-3 font-mono text-brand-cyan font-medium">{c.case_code}</td>
                        <td className="py-3 pr-2">
                          <div className="font-semibold text-white group-hover:text-brand-cyan transition-colors">{c.title}</div>
                          <div className="text-[11px] text-slate-400">{c.case_type.replace(/_/g, ' ')}</div>
                        </td>
                        <td className="py-3 text-slate-300">{c.case_type.replace(/_/g, ' ')}</td>
                        <td className="py-3 font-mono text-[11px] text-slate-400">{formatDate(c.updated_at)}</td>
                        <td className="py-3">
                          <StatusBadge status={caseStatusToVariant(c.status)} />
                        </td>
                        <td className="py-3 text-right">
                          <svg className="w-4 h-4 text-slate-400 group-hover:text-white transition-colors inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                          </svg>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Priority Action Queue */}
          <div className="lg:col-span-5 bg-brand-panel border border-brand-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-white tracking-wide">Priority Action Queue</h2>
              <span className="text-xs text-brand-cyan flex items-center gap-1 font-medium">
                {leadsTotal > 0 ? `${leadsTotal} Leads Active` : 'Automated Review'}
              </span>
            </div>
            <div className="space-y-2.5">
              {leads.length > 0 ? (
                leads.slice(0, 4).map((lead) => {
                  const color: 'red' | 'amber' | 'cyan' =
                    lead.priority === 'HIGH' ? 'red' : lead.priority === 'REVIEW' ? 'amber' : 'cyan'
                  const badge =
                    lead.priority === 'HIGH' ? 'High Priority' : lead.priority === 'REVIEW' ? 'Needs Review' : 'Potential Lead'
                  const targetCase = lead.source_case_ids[0] || lead.target_case_ids[0]
                  return (
                    <ActionQueueItem
                      key={lead.lead_id}
                      title={lead.prediction_type}
                      badge={badge}
                      color={color}
                      description={
                        <div>
                          <div className="flex items-center gap-1 font-mono text-xs">
                            <span className="text-brand-cyan">{lead.source_entity}</span>
                            <span className="text-slate-500">↔</span>
                            <span className="text-white">{lead.target_entity}</span>
                          </div>
                          <p className="text-[11px] text-slate-300 mt-1 line-clamp-2">
                            Score: {(lead.confidence).toFixed(2)} · {lead.explanation}
                          </p>
                        </div>
                      }
                      timeAgo="Active"
                      icon={
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                        </svg>
                      }
                      onReview={() => router.push(`/leads/${encodeURIComponent(lead.lead_id)}`)}
                    />
                  )
                })
              ) : (
                <div className="p-6 text-center text-xs text-slate-400 border border-dashed border-brand-border rounded-lg">
                  No authorized leads queued. Ingest evidence or inspect{' '}
                  <Link href="/leads" className="text-brand-cyan hover:underline">Lead Queue</Link>.
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Recent Evidence Ingestion */}
        <section className="bg-brand-panel border border-brand-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-white tracking-wide">Recent Evidence Ingestion</h2>
            <Link href="/import" className="text-xs text-brand-cyan hover:underline flex items-center gap-1 font-medium">
              Import Evidence <span>→</span>
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead>
                <tr className="border-b border-brand-border text-[11px] font-mono uppercase text-slate-400">
                  <th className="pb-2.5 font-medium">File Name</th>
                  <th className="pb-2.5 font-medium">Case</th>
                  <th className="pb-2.5 font-medium">Source</th>
                  <th className="pb-2.5 font-medium">Ingested On</th>
                  <th className="pb-2.5 font-medium">Integrity</th>
                  <th className="pb-2.5 font-medium text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/40">
                {recentEvidence.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-slate-400">
                      No uploaded evidence items in authorized cases yet.
                    </td>
                  </tr>
                ) : recentEvidence.map((e) => (
                  <tr
                    key={e.id}
                    onClick={() => router.push(`/cases/${e.case_id}/evidence`)}
                    className="hover:bg-brand-surface/70 cursor-pointer transition-colors group"
                  >
                    <td className="py-3 font-mono text-white flex items-center space-x-2">
                      <svg className="w-4 h-4 text-slate-400 group-hover:text-brand-cyan shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                      </svg>
                      <span className="group-hover:text-brand-cyan transition-colors">{e.original_filename}</span>
                    </td>
                    <td className="py-3 font-mono text-brand-cyan">{e.case_code ?? e.case_id.slice(0, 8)}</td>
                    <td className="py-3 text-slate-400">{e.source_label ?? 'Evidence'}</td>
                    <td className="py-3 font-mono text-[11px] text-slate-400">{formatDate(e.uploaded_at)}</td>
                    <td className="py-3"><StatusBadge status={e.integrity_status.toLowerCase().replace('_', '-')} /></td>
                    <td className="py-3 text-right"><StatusBadge status={e.parsing_status.toLowerCase().replace('_', '-')} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Footer */}
        <footer className="pt-2 text-[10px] font-mono text-slate-400 flex items-center justify-between border-t border-brand-border/40">
          <div>SPYDER-DETECT v1.0.0 // SECURE ANALYSIS PLATFORM</div>
          <div>SECURE | ANALYSE | EMPOWER</div>
        </footer>
      </div>

      {/* Case detail modal */}
      {selectedCase && (
        <Modal
          open={!!selectedCase}
          onClose={() => setSelected(null)}
          title={selectedCase.title}
          subtitle={selectedCase.case_type.replace(/_/g, ' ')}
          footer={
            <div className="flex items-center justify-between">
              <Link
                href={`/cases/${selectedCase.id}/graph`}
                className="text-xs text-brand-cyan hover:underline font-mono flex items-center gap-1.5"
              >
                Open Knowledge Graph →
              </Link>
              <button
                onClick={() => setSelected(null)}
                className="px-4 py-1.5 text-xs bg-brand-cyan hover:bg-brand-cyan/80 text-black font-semibold rounded"
              >
                Close
              </button>
            </div>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-3 gap-3">
              <div className="p-2.5 rounded bg-brand-surface border border-brand-border">
                <span className="text-[10px] font-mono text-slate-400 block uppercase">Case Code</span>
                <span className="text-brand-cyan font-mono font-semibold text-xs mt-0.5 block">{selectedCase.case_code}</span>
              </div>
              <div className="p-2.5 rounded bg-brand-surface border border-brand-border">
                <span className="text-[10px] font-mono text-slate-400 block uppercase">Status</span>
                <div className="mt-0.5"><StatusBadge status={caseStatusToVariant(selectedCase.status)} /></div>
              </div>
              <div className="p-2.5 rounded bg-brand-surface border border-brand-border">
                <span className="text-[10px] font-mono text-slate-400 block uppercase">Updated</span>
                <span className="text-slate-300 font-mono text-[11px] mt-0.5 block">{formatDate(selectedCase.updated_at)}</span>
              </div>
            </div>
            {selectedCase.description && (
              <p className="text-slate-300 leading-relaxed">{selectedCase.description}</p>
            )}
            <div className="p-3 bg-brand-surface/60 rounded border border-brand-border/60">
              <div className="text-[11px] font-semibold text-slate-200">Chain of Custody</div>
              <p className="text-[11px] text-slate-400 mt-1">
                All evidence for this docket has SHA-256 integrity tokens. Evidence chain is cryptographically sealed.
              </p>
            </div>
          </div>
        </Modal>
      )}
    </AppShell>
  )
}
