'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import { casesApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case, TimelineEvent } from '@/types'

export default function UnifiedTimelinePage() {
  const router = useRouter()
  const [cases, setCases] = useState<Case[]>([])
  const [caseId, setCaseId] = useState('')
  const [modality, setModality] = useState('')
  const [entity, setEntity] = useState('')
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    casesApi.list().then(({ data }) => {
      setCases(data)
      if (data.length > 0) setCaseId(data[0].id)
    }).catch(() => {})
  }, [router])

  const loadTimeline = useCallback(async () => {
    if (!caseId) return
    setLoading(true)
    try {
      const { data } = await casesApi.timeline(caseId, {
        modality: modality || undefined,
        entity: entity.trim() || undefined,
        limit: 150,
      })
      setEvents(data.events ?? [])
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [caseId, modality, entity])

  useEffect(() => {
    loadTimeline()
  }, [loadTimeline])

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <section className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-brand-border/40 pb-4">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">Unified Evidence Timeline</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Chronological reconstruction from active normalized evidence with SHA-256 provenance
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <select
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="bg-brand-panel border border-brand-border rounded px-2.5 py-1.5 text-slate-200"
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id}>{c.case_code} — {c.title}</option>
              ))}
            </select>
            <select
              value={modality}
              onChange={(e) => setModality(e.target.value)}
              className="bg-brand-panel border border-brand-border rounded px-2.5 py-1.5 text-slate-200"
            >
              <option value="">All Modalities</option>
              <option value="CDR">CDR</option>
              <option value="TRANSACTION">TRANSACTION</option>
              <option value="TRAVEL">TRAVEL</option>
              <option value="VEHICLE">VEHICLE</option>
              <option value="DEVICE">DEVICE</option>
              <option value="CHAT">CHAT</option>
              <option value="PERSONS">PERSONS</option>
            </select>
            <input
              value={entity}
              onChange={(e) => setEntity(e.target.value)}
              placeholder="Filter participant..."
              className="bg-brand-panel border border-brand-border rounded px-2.5 py-1.5 text-slate-200"
            />
          </div>
        </section>

        {loading ? (
          <div className="text-xs text-slate-400 py-12 text-center">Reconstructing timeline…</div>
        ) : events.length === 0 ? (
          <div className="bg-brand-panel border border-brand-border rounded-xl p-10 text-center text-xs text-slate-400">
            No timeline events found for this case filter.
          </div>
        ) : (
          <div className="space-y-2.5">
            {events.map((ev) => (
              <div key={ev.id} className="bg-brand-panel border border-brand-border rounded-xl p-4 text-xs space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-mono">
                    <span className="px-2 py-0.5 rounded bg-brand-cyan/10 text-brand-cyan border border-brand-cyan/30 font-semibold">
                      {ev.modality}
                    </span>
                    <span className="text-white">{ev.timestamp}</span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    {ev.provenance.source_file} #{ev.provenance.source_row} · {ev.provenance.evidence_code}
                  </div>
                </div>
                {ev.participants.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {ev.participants.map((p) => (
                      <Link
                        key={p}
                        href={`/entities/${encodeURIComponent(p)}`}
                        className="px-2 py-0.5 rounded bg-[#070D14] border border-brand-border font-mono text-[11px] text-slate-200 hover:border-brand-cyan"
                      >
                        {p}
                      </Link>
                    ))}
                  </div>
                )}
                <pre className="bg-[#070D14] border border-brand-border/60 rounded p-2.5 font-mono text-[11px] text-slate-400 overflow-x-auto">
                  {JSON.stringify(ev.summary)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}
