'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import { intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { EntityProfile } from '@/types'

export default function EntityProfilePage() {
  const router = useRouter()
  const { entityId } = useParams<{ entityId: string }>()
  const decodedId = decodeURIComponent(entityId)

  const [profile, setProfile] = useState<EntityProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    intelligenceApi.getEntityProfile(decodedId)
      .then(({ data }) => setProfile(data))
      .catch((err) => {
        const status = err?.response?.status
        setError(status === 403 ? 'Access denied to cases associated with this entity.' : `Entity '${decodedId}' not found in authorized records.`)
      })
      .finally(() => setLoading(false))
  }, [decodedId, router])

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <div className="flex items-center justify-between">
          <Link href="/leads" className="text-xs text-brand-cyan hover:underline font-mono">← Back</Link>
        </div>

        {loading ? (
          <div className="text-xs text-slate-400 py-12 text-center">Loading authorized entity dossier…</div>
        ) : error ? (
          <div className="bg-brand-panel border border-brand-red/40 rounded-xl p-6 text-xs text-brand-red">{error}</div>
        ) : profile && (
          <div className="space-y-5">
            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-mono text-brand-cyan uppercase">Observational Entity Profile</div>
                  <h1 className="text-xl font-bold text-white font-mono mt-0.5">{profile.entity_id}</h1>
                  {profile.identifiers.length > 0 && (
                    <div className="text-xs text-slate-300 mt-1">Observed names: {profile.identifiers.join(', ')}</div>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {profile.associated_cases.map((c) => (
                    <Link
                      key={c.case_id}
                      href={`/cases/${c.case_id}/graph`}
                      className="px-2.5 py-1 rounded bg-brand-cyan/10 border border-brand-cyan/30 font-mono text-[11px] text-brand-cyan hover:bg-brand-cyan/20"
                    >
                      {c.case_code} →
                    </Link>
                  ))}
                </div>
              </div>
              <div className="bg-brand-surface/70 border border-brand-amber/30 rounded px-3 py-2 text-[11px] text-slate-300">
                {profile.disclaimer}
              </div>
            </section>

            {/* Observable attributes */}
            <section className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
              {[
                { label: 'Phones', items: profile.phones, color: 'text-brand-green' },
                { label: 'Devices / IMEIs', items: profile.devices, color: 'text-brand-cyan' },
                { label: 'Vehicles', items: profile.vehicles, color: 'text-brand-purple' },
                { label: 'Locations', items: profile.locations, color: 'text-brand-amber' },
              ].map((blk) => (
                <div key={blk.label} className="bg-brand-panel border border-brand-border rounded-xl p-4">
                  <div className={`text-[11px] font-mono uppercase font-semibold mb-2 ${blk.color}`}>{blk.label}</div>
                  {blk.items.length === 0 ? (
                    <div className="text-slate-500">None observed</div>
                  ) : (
                    <ul className="space-y-1 font-mono text-slate-200">
                      {blk.items.map((x) => <li key={x}>{x}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </section>

            {/* Provisional Identity Hypotheses (strictly separated) */}
            <section className="bg-brand-panel border border-brand-purple/40 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-white">Provisional Identity Hypotheses ({profile.identity_hypotheses.length})</h2>
                <Link href="/entity-resolution" className="text-xs text-brand-cyan hover:underline">Open Workbench →</Link>
              </div>
              {profile.identity_hypotheses.length === 0 ? (
                <p className="text-xs text-slate-400">No authorized identity hypotheses involving this entity.</p>
              ) : (
                <div className="space-y-2 text-xs">
                  {profile.identity_hypotheses.map((h) => (
                    <div key={h.id} className="bg-[#070D14] border border-brand-border rounded-lg p-3 flex justify-between items-center">
                      <div className="font-mono">
                        <span className="text-brand-cyan">{h.person_a_ref}</span> ({h.case_a_ref}) ≈{' '}
                        <span className="text-brand-purple">{h.person_b_ref}</span> ({h.case_b_ref})
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

            {/* Evidence References & Chronology */}
            <section className="bg-brand-panel border border-brand-border rounded-xl p-5 space-y-3">
              <h2 className="text-sm font-bold text-white">Observed Evidence Records ({profile.evidence_references.length})</h2>
              <div className="space-y-2 max-h-96 overflow-y-auto text-xs">
                {profile.evidence_references.map((er) => (
                  <div key={er.record_id} className="bg-[#070D14] border border-brand-border rounded p-3 flex justify-between gap-3">
                    <div>
                      <span className="font-mono text-brand-cyan">{er.record_type}</span> ·{' '}
                      <span className="font-mono text-slate-400">{er.case_code}</span> ·{' '}
                      <span className="text-slate-300">{er.source_file} #{er.source_row}</span>
                      <pre className="text-[11px] font-mono text-slate-400 mt-1 overflow-x-auto">
                        {JSON.stringify(er.normalized_record)}
                      </pre>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  )
}
