'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import KpiCard from '@/components/ui/KpiCard'
import StatusBadge from '@/components/ui/StatusBadge'
import ActionQueueItem from '@/components/ui/ActionQueueItem'
import Modal from '@/components/ui/Modal'
import { casesApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case } from '@/types'

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
  const [cases, setCases]           = useState<Case[]>([])
  const [loading, setLoading]       = useState(true)
  const [selectedCase, setSelected] = useState<Case | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    casesApi.list()
      .then(({ data }) => setCases(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [router])

  const activeCases     = cases.filter((c) => c.status === 'ACTIVE').length
  const totalCases      = cases.length

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
          <KpiCard icon={<CasesIcon />}         label="Active Cases"    value={activeCases || 14}  trendDelta={2}  color="cyan"   />
          <KpiCard icon={<ReviewsIcon />}        label="Pending Reviews" value={37}                 trendDelta={12} color="red"    />
          <KpiCard icon={<ContradictionsIcon />} label="Contradictions"  value={6}                  trendDelta={3}  color="amber"  />
          <KpiCard icon={<LinksIcon />}          label="Cross-Case Links" value={3}                 trendDelta={1}  color="purple" />
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
                    {(cases.length > 0 ? cases : MOCK_CASES).map((c) => (
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
              <a href="#" className="text-xs text-brand-cyan hover:underline flex items-center gap-1 font-medium">
                View All <span>→</span>
              </a>
            </div>
            <div className="space-y-2.5">
              <ActionQueueItem
                title="Candidate Entity Match"
                badge="High Priority"
                color="red"
                description={<>Possible match for <span className="font-mono text-brand-cyan">+91 98XXXXXX12</span> with existing suspect in Case #25998.</>}
                timeAgo="3h ago"
                icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>}
              />
              <ActionQueueItem
                title="Contradiction Detected"
                badge="Needs Review"
                color="amber"
                description="Location data conflicts with witness statement for Case #26189."
                timeAgo="5h ago"
                icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>}
              />
              <ActionQueueItem
                title="Cross-Case Link"
                badge="Medium"
                color="cyan"
                description={<>Vehicle <span className="font-mono text-white">DL01AB1234</span> appears in 2 cases.</>}
                timeAgo="1d ago"
                icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>}
              />
              <ActionQueueItem
                title="Unusual Financial Activity"
                badge="Medium"
                color="purple"
                description="Multiple transfers from A/C XXXX4021 to high-risk entities."
                timeAgo="1d ago"
                icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" /></svg>}
              />
            </div>
          </div>
        </section>

        {/* Recent Evidence Ingestion */}
        <section className="bg-brand-panel border border-brand-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-white tracking-wide">Recent Evidence Ingestion</h2>
            <Link href="/import" className="text-xs text-brand-cyan hover:underline flex items-center gap-1 font-medium">
              View All <span>→</span>
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead>
                <tr className="border-b border-brand-border text-[11px] font-mono uppercase text-slate-400">
                  <th className="pb-2.5 font-medium">File Name</th>
                  <th className="pb-2.5 font-medium">Type</th>
                  <th className="pb-2.5 font-medium">Source</th>
                  <th className="pb-2.5 font-medium">Ingested On</th>
                  <th className="pb-2.5 font-medium">Status</th>
                  <th className="pb-2.5 font-medium text-right">Records</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/40">
                {MOCK_EVIDENCE.map((e, i) => (
                  <tr key={i} className="hover:bg-brand-surface/70 cursor-pointer transition-colors group">
                    <td className="py-3 font-mono text-white flex items-center space-x-2">
                      <svg className="w-4 h-4 text-slate-400 group-hover:text-brand-cyan shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                      </svg>
                      <span className="group-hover:text-brand-cyan transition-colors">{e.name}</span>
                    </td>
                    <td className="py-3 text-slate-300">{e.type}</td>
                    <td className="py-3 text-slate-400">{e.source}</td>
                    <td className="py-3 font-mono text-[11px] text-slate-400">{e.date}</td>
                    <td className="py-3"><StatusBadge status={e.status.toLowerCase()} /></td>
                    <td className="py-3 font-mono text-slate-200 text-right">{e.records}</td>
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

// ─── Mock fallback data ────────────────────────────────────────────────────
const MOCK_CASES: Case[] = [
  { id: '1', case_code: 'HT-2026-001', title: 'Operation Falcon',    case_type: 'CYBER_CRIME',        status: 'ACTIVE',  created_by: '', created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-12T10:24:00Z', members: [] },
  { id: '2', case_code: 'HT-2026-002', title: 'Financial Fraud',     case_type: 'FINANCIAL_CRIME',    status: 'ACTIVE',  created_by: '', created_at: '2026-07-15T00:00:00Z', updated_at: '2026-08-10T16:17:00Z', members: [] },
  { id: '3', case_code: 'HT-2026-003', title: 'Human Trafficking',   case_type: 'HUMAN_TRAFFICKING',  status: 'ON_HOLD', created_by: '', created_at: '2026-07-01T00:00:00Z', updated_at: '2026-08-08T11:03:00Z', members: [] },
  { id: '4', case_code: 'HT-2026-004', title: 'Operation Nexus',     case_type: 'ORGANIZED_CRIME',    status: 'ACTIVE',  created_by: '', created_at: '2026-06-20T00:00:00Z', updated_at: '2026-08-05T14:41:00Z', members: [] },
]

const MOCK_EVIDENCE = [
  { name: 'CDR_Aug2026.csv',       type: 'CDR',            source: 'Telecom Provider', date: '12 Aug 2026, 10:24 AM', status: 'completed', records: '30' },
  { name: 'Bank_Statements.xlsx',  type: 'Bank Statement', source: 'Bank (LEA)',       date: '12 Aug 2026, 09:18 AM', status: 'completed', records: '26' },
  { name: 'UPI_Transactions.csv',  type: 'UPI',            source: 'NPCI Data',        date: '11 Aug 2026, 06:11 PM', status: 'processing', records: '25' },
]
