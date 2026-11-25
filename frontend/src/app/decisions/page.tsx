'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import { intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { DecisionHistoryItem, ModelRegistryItem } from '@/types'

export default function DecisionHistoryPage() {
  const router = useRouter()
  const [decisions, setDecisions] = useState<DecisionHistoryItem[]>([])
  const [models, setModels] = useState<ModelRegistryItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    Promise.all([
      intelligenceApi.listDecisions(150).then(({ data }) => setDecisions(data.decisions ?? [])).catch(() => {}),
      intelligenceApi.listModels().then(({ data }) => setModels(data.models ?? [])).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [router])

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-6 bg-brand-bg min-h-full">
        <section className="border-b border-brand-border/40 pb-4">
          <h1 className="text-xl font-bold text-white tracking-tight">Review Decisions &amp; Model Provenance</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Case-isolated investigator adjudications alongside registered ML model artifacts and schemas.
          </p>
        </section>

        <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
          <h2 className="text-sm font-bold text-white">Active Model Registry ({models.length})</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {models.map((m, i) => (
              <div key={m.id || i} className="bg-[#070D14] border border-brand-border rounded-lg p-3.5 space-y-1">
                <div className="flex items-center justify-between font-mono">
                  <span className="text-brand-cyan font-semibold">{m.model_name}</span>
                  <span className="px-2 py-0.5 rounded bg-brand-green/10 text-brand-green border border-brand-green/30 text-[10px]">
                    {m.version}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 font-mono">Schema: {m.feature_schema_version}</div>
                <div className="text-[10px] text-slate-500 font-mono truncate">{m.artifact_uri}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
          <h2 className="text-sm font-bold text-white">Authorized Decision &amp; Note Log ({decisions.length})</h2>
          {loading ? (
            <div className="text-xs text-slate-400 py-8 text-center">Loading decision log…</div>
          ) : decisions.length === 0 ? (
            <div className="text-xs text-slate-400 py-8 text-center">No review decisions recorded in your authorized cases yet.</div>
          ) : (
            <div className="space-y-2.5 text-xs">
              {decisions.map((d) => (
                <div key={d.id} className="bg-[#070D14] border border-brand-border rounded-lg p-3.5 space-y-1">
                  <div className="flex flex-wrap items-center justify-between gap-2 font-mono">
                    <span className="text-brand-cyan font-semibold">{d.category}</span>
                    <span className="text-[10px] text-slate-400">{new Date(d.created_at).toLocaleString('en-GB')}</span>
                  </div>
                  <div className="text-white font-medium">{d.summary}</div>
                  <div className="text-slate-300 text-[11px]">Rationale: {d.rationale}</div>
                  <div className="text-[10px] font-mono text-slate-500">Cases: {d.cases.join(', ')}</div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  )
}
