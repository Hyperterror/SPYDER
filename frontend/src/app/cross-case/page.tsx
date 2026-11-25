'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import { intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { CrossCaseLeadSummary, IdentityHypothesis } from '@/types'

export default function CrossCasePage() {
  const router = useRouter()
  const [bridges, setBridges] = useState<CrossCaseLeadSummary[]>([])
  const [hyps, setHyps] = useState<IdentityHypothesis[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    Promise.all([
      intelligenceApi.getCrossCase({ limit: 100 }).then(({ data }) => setBridges(data.cross_case_leads ?? [])).catch(() => {}),
      intelligenceApi.listIdentityHypotheses({ limit: 50 }).then(({ data }) => setHyps(data.hypotheses ?? [])).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [router])

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <section className="border-b border-brand-border/40 pb-4">
          <h1 className="text-xl font-bold text-white tracking-tight">Cross-Case Intelligence Bridges</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Strict authorization enforced: bridges are surfaced only when you hold clearance for every linked case.
          </p>
        </section>

        {loading ? (
          <div className="text-xs text-slate-400 py-12 text-center">Evaluating authorized cross-case bridges…</div>
        ) : (
          <div className="space-y-6">
            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-white">Cross-Case Link Leads ({bridges.length})</h2>
                <Link href="/leads" className="text-xs text-brand-cyan hover:underline">Full Lead Queue →</Link>
              </div>
              {bridges.length === 0 ? (
                <p className="text-xs text-slate-400">No cross-case leads within your authorized case dossiers.</p>
              ) : (
                <div className="space-y-2.5 text-xs">
                  {bridges.map((b) => (
                    <div key={b.lead_id} className="bg-[#070D14] border border-brand-border rounded-lg p-3.5 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="font-mono text-white font-semibold">
                          {b.source_entity} <span className="text-slate-500">↔</span> {b.target_entity}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono mt-1">
                          {b.source_cases.join(', ')} ↔ {b.target_cases.join(', ')} · Modalities: {b.supporting_modalities.join(', ') || 'GRAPH'}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-brand-cyan font-bold">{(b.confidence * 100).toFixed(1)}%</span>
                        <StatusBadge status={b.priority.toLowerCase()} />
                        <Link
                          href={`/leads/${encodeURIComponent(b.lead_id)}`}
                          className="px-2.5 py-1 rounded bg-brand-cyan/15 border border-brand-cyan/40 text-brand-cyan"
                        >
                          Inspect
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-white">Cross-Case Identity Hypotheses ({hyps.length})</h2>
                <Link href="/entity-resolution" className="text-xs text-brand-cyan hover:underline">ER Workbench →</Link>
              </div>
              {hyps.length === 0 ? (
                <p className="text-xs text-slate-400">No authorized cross-case identity hypotheses found.</p>
              ) : (
                <div className="space-y-2 text-xs">
                  {hyps.map((h) => (
                    <div key={h.id} className="bg-[#070D14] border border-brand-border rounded-lg p-3 flex justify-between items-center">
                      <div className="font-mono text-slate-200">
                        <span className="text-brand-cyan">{h.case_a_ref}</span>: {h.person_a_name} ({h.person_a_ref}) ↔{' '}
                        <span className="text-brand-purple">{h.case_b_ref}</span>: {h.person_b_name} ({h.person_b_ref})
                      </div>
                      <div className="font-mono text-[11px] space-x-2">
                        <span className="text-white">{(h.match_probability * 100).toFixed(1)}%</span>
                        <span className="text-brand-amber">{h.status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </AppShell>
  )
}
