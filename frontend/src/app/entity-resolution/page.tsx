'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/ToastNotification'
import { intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { IdentityHypothesis } from '@/types'

export default function EntityResolutionWorkbenchPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [hypotheses, setHypotheses] = useState<IdentityHypothesis[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<IdentityHypothesis | null>(null)
  const [rationale, setRationale] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await intelligenceApi.listIdentityHypotheses({
        status: statusFilter || undefined,
        limit: 100,
      })
      setHypotheses(data.hypotheses ?? [])
    } catch {
      setHypotheses([])
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    loadList()
  }, [loadList, router])

  const openDetail = async (id: string) => {
    try {
      const { data } = await intelligenceApi.getIdentityHypothesis(id)
      setDetail(data)
      setRationale('')
    } catch {
      toast('Access denied or hypothesis unavailable', 'error')
    }
  }

  const submitDecision = async (decision: 'ACCEPTED' | 'REJECTED' | 'DISPUTED') => {
    if (!detail) return
    if (rationale.trim().length < 3) {
      toast('Enter an adjudication rationale (min 3 characters)', 'warn')
      return
    }
    setSubmitting(true)
    try {
      const { data } = await intelligenceApi.reviewIdentityHypothesis(detail.id, decision, rationale.trim())
      setDetail(data)
      toast(`Hypothesis marked ${decision} (provisional audit recorded)`, 'info')
      await loadList()
    } catch {
      toast('Failed to record decision', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <section className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-brand-border/40 pb-4">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">Entity Resolution Workbench</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Provisional cross-case identity hypotheses requiring human adjudication (never auto-merged)
            </p>
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-brand-panel border border-brand-border rounded px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="">All Statuses</option>
            <option value="PENDING_REVIEW">PENDING REVIEW</option>
            <option value="CANDIDATE">CANDIDATE</option>
            <option value="ACCEPTED">ACCEPTED</option>
            <option value="DISPUTED">DISPUTED</option>
            <option value="REJECTED">REJECTED</option>
          </select>
        </section>

        {loading ? (
          <div className="text-xs text-slate-400 py-12 text-center">Loading identity hypotheses…</div>
        ) : hypotheses.length === 0 ? (
          <div className="bg-brand-panel border border-brand-border rounded-xl p-10 text-center text-xs text-slate-400">
            No cross-case identity hypotheses available in your authorized scope.
          </div>
        ) : (
          <div className="space-y-3">
            {hypotheses.map((h) => (
              <div key={h.id} className="bg-brand-panel border border-brand-border hover:border-brand-cyan/40 rounded-xl p-4 transition">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
                      <span className="text-brand-cyan font-semibold">{h.case_a_ref}</span>
                      <span className="text-white">{h.person_a_name} ({h.person_a_ref})</span>
                      <span className="text-slate-500">≈</span>
                      <span className="text-brand-purple font-semibold">{h.case_b_ref}</span>
                      <span className="text-white">{h.person_b_name} ({h.person_b_ref})</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-2 text-[11px]">
                      <span className="px-2 py-0.5 rounded bg-brand-surface border border-brand-border font-mono text-brand-cyan">
                        Match Prob: {(h.match_probability * 100).toFixed(1)}%
                      </span>
                      <span className="px-2 py-0.5 rounded bg-brand-surface border border-brand-border font-mono text-slate-300">
                        {h.confidence_tier}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-brand-surface border border-brand-border font-mono text-brand-amber">
                        {h.status}
                      </span>
                      {h.blocking_reasons.slice(0, 3).map((br, i) => (
                        <span key={i} className="text-slate-400 font-mono text-[10px]">{br}</span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => openDetail(h.id)}
                      className="px-3 py-1.5 text-xs font-semibold bg-brand-cyan/15 hover:bg-brand-cyan/25 border border-brand-cyan/40 text-brand-cyan rounded transition"
                    >
                      Compare Side-by-Side →
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {detail && (
        <Modal
          open={!!detail}
          onClose={() => setDetail(null)}
          title={`Side-by-Side Identity Comparison`}
          subtitle={`${detail.person_a_ref} (${detail.case_a_ref}) vs ${detail.person_b_ref} (${detail.case_b_ref}) · Prob ${(detail.match_probability * 100).toFixed(1)}%`}
          maxWidth="max-w-4xl"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[{ title: 'Observation A', refId: detail.person_a_ref, prof: detail.profile_a }, { title: 'Observation B', refId: detail.person_b_ref, prof: detail.profile_b }].map((side) => (
                <div key={side.title} className="bg-[#070D14] border border-brand-border rounded-lg p-3.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-brand-cyan font-semibold">{side.title}</span>
                    <Link href={`/entities/${encodeURIComponent(side.refId)}`} className="text-[11px] text-brand-cyan hover:underline">
                      Open Entity →
                    </Link>
                  </div>
                  <pre className="text-[11px] font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(side.prof ?? {}, null, 2)}
                  </pre>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-brand-surface/70 border border-brand-green/30 rounded-lg p-3">
                <div className="font-semibold text-brand-green mb-1">Supporting Signals</div>
                {detail.supporting_evidence.length === 0 ? (
                  <div className="text-slate-400">None listed</div>
                ) : detail.supporting_evidence.map((s, i) => (
                  <div key={i} className="text-slate-200 text-[11px]">• {s}</div>
                ))}
              </div>
              <div className="bg-brand-surface/70 border border-brand-red/30 rounded-lg p-3">
                <div className="font-semibold text-brand-red mb-1">Conflicting Signals</div>
                {detail.conflicting_evidence.length === 0 ? (
                  <div className="text-slate-400">No conflicting signals recorded</div>
                ) : detail.conflicting_evidence.map((c, i) => (
                  <div key={i} className="text-slate-200 text-[11px]">• {c}</div>
                ))}
              </div>
            </div>

            <div className="border-t border-brand-border pt-3 space-y-2">
              <label className="text-[11px] font-mono uppercase text-slate-400 block">Adjudication Rationale</label>
              <input
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="Explain evidentiary verification or reason for rejection/dispute..."
                className="w-full bg-[#070D14] border border-brand-border rounded px-3 py-2 text-slate-100"
              />
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  onClick={() => submitDecision('ACCEPTED')}
                  disabled={submitting}
                  className="px-3 py-1.5 rounded bg-brand-green text-black font-semibold disabled:opacity-50"
                >
                  Accept Hypothesis
                </button>
                <button
                  onClick={() => submitDecision('DISPUTED')}
                  disabled={submitting}
                  className="px-3 py-1.5 rounded bg-brand-amber text-black font-semibold disabled:opacity-50"
                >
                  Mark Disputed
                </button>
                <button
                  onClick={() => submitDecision('REJECTED')}
                  disabled={submitting}
                  className="px-3 py-1.5 rounded bg-brand-red text-white font-semibold disabled:opacity-50"
                >
                  Reject Match
                </button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </AppShell>
  )
}
