'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import { useToast } from '@/components/ui/ToastNotification'
import { intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { InvestigationLead } from '@/types'

const LEAD_STATUSES = [
  'UNDER_REVIEW',
  'ACCEPTED_FOR_FURTHER_INVESTIGATION',
  'REQUIRES_MORE_EVIDENCE',
  'REJECTED',
  'CLOSED',
]

export default function LeadDetailPage() {
  const router = useRouter()
  const { leadId } = useParams<{ leadId: string }>()
  const { toast } = useToast()

  const [lead, setLead] = useState<InvestigationLead | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newStatus, setNewStatus] = useState('ACCEPTED_FOR_FURTHER_INVESTIGATION')
  const [rationale, setRationale] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await intelligenceApi.getLead(decodeURIComponent(leadId))
      setLead(data)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setError(status === 403 ? 'Access denied to one or more cases involved in this lead.' : 'Lead not found.')
    } finally {
      setLoading(false)
    }
  }, [leadId])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    load()
  }, [load, router])

  const submitReview = async (e: React.FormEvent) => {
    e.preventDefault()
    if (rationale.trim().length < 3) {
      toast('Enter a rationale (at least 3 characters)', 'warn')
      return
    }
    setSubmitting(true)
    try {
      await intelligenceApi.reviewLead(decodeURIComponent(leadId), newStatus, rationale.trim())
      toast(`Lead marked ${newStatus}`, 'info')
      setRationale('')
      await load()
    } catch {
      toast('Failed to submit lead review', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <div className="flex items-center justify-between">
          <Link href="/leads" className="text-xs text-brand-cyan hover:underline font-mono">
            ← Back to Lead Queue
          </Link>
        </div>

        {loading ? (
          <div className="text-xs text-slate-400 py-12 text-center">Loading lead details…</div>
        ) : error ? (
          <div className="bg-brand-panel border border-brand-red/40 rounded-xl p-6 text-xs text-brand-red">{error}</div>
        ) : lead && (
          <div className="space-y-5">
            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-xs font-mono">
                    <span className="text-brand-cyan font-semibold">{lead.lead_id}</span>
                    {lead.is_cross_case && (
                      <span className="px-2 py-0.5 rounded bg-brand-purple/15 text-brand-purple border border-brand-purple/30 text-[10px]">
                        CROSS-CASE
                      </span>
                    )}
                    <StatusBadge status={lead.priority.toLowerCase()} />
                    <span className="px-2 py-0.5 rounded bg-brand-surface border border-brand-border text-slate-200 text-[10px]">
                      {lead.status ?? 'NEW'}
                    </span>
                  </div>
                  <h1 className="text-lg font-bold text-white font-mono mt-2">
                    {lead.source_entity} <span className="text-slate-500">↔</span> {lead.target_entity}
                  </h1>
                  <p className="text-xs text-slate-300 mt-2 leading-relaxed">{lead.explanation}</p>
                </div>

                <div className="bg-[#070D14] border border-brand-border rounded-lg px-4 py-3 text-right shrink-0">
                  <div className="text-[10px] font-mono uppercase text-slate-400">Model Confidence</div>
                  <div className="text-2xl font-bold font-mono text-brand-cyan">
                    {(lead.confidence * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    {lead.model_version ?? 'graphsage-1.0.0'} · {lead.evidence_strength}
                  </div>
                </div>
              </div>

              {lead.caveats.length > 0 && (
                <div className="bg-brand-amber/10 border border-brand-amber/30 rounded-lg p-3 text-xs text-brand-amber space-y-1">
                  <div className="font-semibold">Caveats &amp; Limitations</div>
                  {lead.caveats.map((c, idx) => (
                    <div key={idx} className="text-[11px] text-slate-200">• {c}</div>
                  ))}
                </div>
              )}

              {lead.common_intermediates.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-[11px] text-slate-400 mr-1">Intermediates:</span>
                  {lead.common_intermediates.map((item, i) => (
                    <span key={i} className="px-2 py-0.5 rounded bg-brand-surface border border-brand-border font-mono text-[11px] text-brand-cyan">
                      {item}
                    </span>
                  ))}
                </div>
              )}
            </section>

            {/* Provenance Records */}
            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
              <h2 className="text-sm font-bold text-white">Supporting Evidence Provenance ({lead.supporting_records.length})</h2>
              {lead.supporting_records.length === 0 ? (
                <p className="text-xs text-slate-400">No structured supporting records attached.</p>
              ) : (
                <div className="space-y-2">
                  {lead.supporting_records.map((rec, i) => (
                    <div key={i} className="bg-[#070D14] border border-brand-border rounded-lg p-3 text-xs flex flex-wrap justify-between gap-2">
                      <div>
                        <div className="font-mono text-brand-cyan text-[11px]">
                          {rec.evidence_type} {rec.case_id ? `· ${rec.case_id}` : ''}
                        </div>
                        <div className="text-slate-200 mt-0.5">{rec.reason}</div>
                      </div>
                      <div className="text-right font-mono text-[10px] text-slate-400">
                        {rec.source_file && <div>{rec.source_file}{rec.source_row ? ` #${rec.source_row}` : ''}</div>}
                        {rec.timestamp && <div>{rec.timestamp}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Human Review Form */}
            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
              <h2 className="text-sm font-bold text-white">Investigator Review &amp; Adjudication</h2>
              {lead.decision_rationale && (
                <div className="bg-brand-surface border border-brand-border rounded p-3 text-xs text-slate-300">
                  <span className="font-mono text-brand-cyan">Latest Decision Rationale:</span> {lead.decision_rationale}
                </div>
              )}
              <form onSubmit={submitReview} className="space-y-3 text-xs">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <select
                    value={newStatus}
                    onChange={(e) => setNewStatus(e.target.value)}
                    className="bg-[#070D14] border border-brand-border rounded px-3 py-2 text-slate-100"
                  >
                    {LEAD_STATUSES.map((s) => (
                      <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                  <input
                    value={rationale}
                    onChange={(e) => setRationale(e.target.value)}
                    placeholder="Document evidentiary basis for decision..."
                    className="md:col-span-2 bg-[#070D14] border border-brand-border rounded px-3 py-2 text-slate-100"
                  />
                </div>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-brand-cyan hover:bg-brand-cyan/80 text-black font-semibold rounded transition disabled:opacity-50"
                >
                  {submitting ? 'Recording Decision…' : 'Record Review Decision'}
                </button>
              </form>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  )
}
