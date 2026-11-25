'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import { intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { InvestigationLead } from '@/types'

export default function LeadsQueuePage() {
  const router = useRouter()
  const [leads, setLeads] = useState<InvestigationLead[]>([])
  const [total, setTotal] = useState(0)
  const [priorityFilter, setPriorityFilter] = useState('')
  const [crossCaseOnly, setCrossCaseOnly] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const loadLeads = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await intelligenceApi.getLeads({
        priority: priorityFilter || undefined,
        is_cross_case: crossCaseOnly ? true : undefined,
        status_filter: statusFilter || undefined,
        limit: 100,
      })
      setLeads(data.leads ?? [])
      setTotal(data.total ?? 0)
    } catch {
      setLeads([])
    } finally {
      setLoading(false)
    }
  }, [priorityFilter, crossCaseOnly, statusFilter])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    loadLeads()
  }, [loadLeads, router])

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <section className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-brand-border/40 pb-4">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">Investigation Lead Queue</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Evidence-backed candidate associations &amp; cross-case hypotheses ({total} authorized leads)
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="bg-brand-panel border border-brand-border rounded px-2.5 py-1.5 text-slate-200"
            >
              <option value="">All Priorities</option>
              <option value="HIGH">HIGH</option>
              <option value="REVIEW">REVIEW</option>
              <option value="LOW">LOW</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-brand-panel border border-brand-border rounded px-2.5 py-1.5 text-slate-200"
            >
              <option value="">All Statuses</option>
              <option value="NEW">NEW</option>
              <option value="UNDER_REVIEW">UNDER REVIEW</option>
              <option value="REQUIRES_MORE_EVIDENCE">NEEDS MORE EVIDENCE</option>
              <option value="ACCEPTED_FOR_FURTHER_INVESTIGATION">ACCEPTED</option>
              <option value="REJECTED">REJECTED</option>
            </select>
            <label className="flex items-center gap-1.5 bg-brand-panel border border-brand-border rounded px-2.5 py-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={crossCaseOnly}
                onChange={(e) => setCrossCaseOnly(e.target.checked)}
                className="rounded bg-slate-900 border-slate-700 text-brand-cyan"
              />
              <span className="text-slate-300">Cross-Case Only</span>
            </label>
          </div>
        </section>

        <div className="bg-brand-panel/70 border border-brand-amber/30 rounded-lg px-4 py-2.5 text-[11px] text-slate-300">
          <span className="text-brand-amber font-semibold">Investigative Safeguard:</span> Displayed leads are predictive hypotheses requiring investigator verification against primary records. Only leads where every linked case is authorized appear here.
        </div>

        <section className="bg-brand-panel border border-brand-border rounded-xl overflow-hidden">
          {loading ? (
            <div className="p-10 text-center text-xs text-slate-400">Loading authorized leads…</div>
          ) : leads.length === 0 ? (
            <div className="p-10 text-center text-xs text-slate-400">No leads match current filters.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-brand-border bg-brand-surface/50 text-[11px] font-mono uppercase text-slate-400">
                    <th className="py-3 px-4">Lead ID</th>
                    <th className="py-3 px-4">Candidate Link</th>
                    <th className="py-3 px-4">Cases</th>
                    <th className="py-3 px-4">Score</th>
                    <th className="py-3 px-4">Priority</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-border/40">
                  {leads.map((l) => (
                    <tr key={l.lead_id} className="hover:bg-brand-surface/60 transition">
                      <td className="py-3 px-4 font-mono text-brand-cyan">{l.lead_id}</td>
                      <td className="py-3 px-4">
                        <div className="font-mono text-white text-xs">
                          {l.source_entity} <span className="text-slate-500">↔</span> {l.target_entity}
                        </div>
                        <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{l.explanation}</p>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px]">
                        {[...l.source_case_ids, ...l.target_case_ids].join(', ') || '—'}
                        {l.is_cross_case && (
                          <span className="ml-1.5 px-1.5 py-0.5 rounded bg-brand-purple/15 text-brand-purple text-[9px] border border-brand-purple/30">
                            CROSS-CASE
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-white font-semibold">
                        {(l.confidence * 100).toFixed(1)}%
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge status={l.priority.toLowerCase()} />
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-300">
                        {l.status ?? 'NEW'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Link
                          href={`/leads/${encodeURIComponent(l.lead_id)}`}
                          className="px-2.5 py-1 rounded bg-brand-cyan/15 hover:bg-brand-cyan/25 border border-brand-cyan/40 text-brand-cyan font-medium"
                        >
                          Inspect →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  )
}
