'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import { casesApi, intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case } from '@/types'

// Load canvas client-side only
const SpiderCanvas = dynamic(() => import('@/components/SpiderCanvas'), { ssr: false })

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

function caseVariant(s: string) {
  const m: Record<string, string> = { ACTIVE: 'in-progress', ON_HOLD: 'under-review', CLOSED: 'closed', DRAFT: 'draft' }
  return m[s] ?? 'active'
}

const CAPABILITIES = [
  { label: 'Investigation Leads', desc: 'Review ranked hypotheses', href: '/leads', icon: '⚡' },
  { label: 'Entity Resolution', desc: 'Adjudicate identity matches', href: '/entity-resolution', icon: '◈' },
  { label: 'Case Management', desc: 'Organise investigations', href: '/cases', icon: '⬜' },
  { label: 'Statement Lab', desc: 'Verify claims vs evidence', href: '/consistency', icon: '⬛' },
]

export default function MissionControlPage() {
  const router = useRouter()
  const [cases, setCases] = useState<Case[]>([])
  const [leadTotal, setLeadTotal] = useState<number>(0)
  const [hypTotal, setHypTotal] = useState<number>(0)
  const [crossTotal, setCrossTotal] = useState<number>(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    Promise.all([
      casesApi.list().then(({ data }) => setCases(data)).catch(() => {}),
      intelligenceApi.getLeads({ limit: 1 }).then(({ data }) => setLeadTotal(data.total ?? 0)).catch(() => {}),
      intelligenceApi.listIdentityHypotheses({ limit: 1 }).then(({ data }) => setHypTotal(data.total ?? 0)).catch(() => {}),
      intelligenceApi.getCrossCase({ limit: 1 }).then(({ data }) => setCrossTotal(data.total ?? 0)).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [router])

  const STAT_CARDS = [
    { label: 'Authorized Cases', value: String(cases.length), color: 'text-brand-cyan', border: 'border-brand-cyan/20' },
    { label: 'Active Leads', value: String(leadTotal), color: 'text-brand-purple', border: 'border-brand-purple/20' },
    { label: 'Identity Hypotheses', value: String(hypTotal), color: 'text-brand-green', border: 'border-brand-green/20' },
    { label: 'Cross-Case Bridges', value: String(crossTotal), color: 'text-brand-red', border: 'border-brand-red/20' },
  ]

  return (
    <>
      {/* ── Full-screen spider canvas — behind everything ── */}
      <SpiderCanvas opacity={0.4} />

      {/* ── App shell sits on top, with transparent backgrounds ── */}
      <AppShell>
        <div className="relative z-10 px-6 md:px-10 py-6 space-y-8 min-h-full overflow-y-auto">

          {/* Hero */}
          <section className="py-6">
            <div className="space-y-3 max-w-2xl">
              <div className="text-brand-cyan font-semibold text-xs tracking-widest uppercase flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-cyan animate-ping inline-block" />
                SPYDER-DETECT
              </div>
              <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-white">
                From fragments to{' '}
                <span className="text-brand-cyan">clarity.</span>
              </h1>
              <p className="text-slate-400 text-base">
                Unify data. Reveal connections. Support investigations.
              </p>
            </div>
          </section>

          {/* Primary actions */}
          <section className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl">
            <Link
              href="/import"
              className="group relative bg-gradient-to-r from-[#00A8CC] to-brand-cyan p-px rounded-xl hover:shadow-[0_0_25px_rgba(0,229,255,0.3)] transition-all"
            >
              <div className="bg-[#0A1622] group-hover:bg-brand-bg rounded-xl p-5 flex items-center justify-between h-full transition-colors">
                <div className="flex items-center gap-4">
                  <div className="h-12 w-12 rounded-lg bg-brand-cyan/10 border border-brand-cyan/30 flex items-center justify-center text-brand-cyan text-xl">
                    ↑
                  </div>
                  <div>
                    <h3 className="text-white font-semibold text-base group-hover:text-brand-cyan transition-colors">
                      Import Evidence
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">Upload and process new data</p>
                  </div>
                </div>
                <span className="text-brand-cyan group-hover:translate-x-1 transition-transform">→</span>
              </div>
            </Link>

            <Link
              href="/cases"
              className="group bg-brand-surface/80 hover:bg-brand-surface border border-brand-border hover:border-brand-borderLight rounded-xl p-5 flex items-center justify-between transition-all"
            >
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-lg bg-brand-panel border border-brand-border flex items-center justify-center text-slate-300 group-hover:text-brand-cyan transition-colors text-xl">
                  ⊞
                </div>
                <div>
                  <h3 className="text-white font-semibold text-base group-hover:text-brand-cyan transition-colors">
                    Create New Case
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">Start a new investigation</p>
                </div>
              </div>
              <span className="text-slate-400 group-hover:text-brand-cyan group-hover:translate-x-1 transition-all">→</span>
            </Link>
          </section>

          {/* Quick stats */}
          <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {STAT_CARDS.map((s) => (
              <div
                key={s.label}
                className={`bg-brand-panel/80 backdrop-blur border ${s.border} rounded-xl p-4 text-center hover:border-opacity-60 transition-all`}
              >
                <div className={`text-2xl font-extrabold font-mono ${s.color}`}>{s.value}</div>
                <div className="text-[11px] text-slate-400 mt-1">{s.label}</div>
              </div>
            ))}
          </section>

          {/* Capabilities */}
          <section>
            <h2 className="text-sm font-semibold text-slate-300 tracking-wide uppercase mb-4">
              Explore Capabilities
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {CAPABILITIES.map((c) => (
                <Link
                  key={c.label}
                  href={c.href}
                  className="bg-brand-panel/90 backdrop-blur hover:bg-brand-panelHover border border-brand-border hover:border-brand-cyan/40 rounded-xl p-5 transition-all group"
                >
                  <div className="h-10 w-10 rounded-lg bg-brand-cyan/10 border border-brand-cyan/30 flex items-center justify-center text-brand-cyan mb-4 text-lg">
                    {c.icon}
                  </div>
                  <h3 className="text-white font-medium text-sm group-hover:text-brand-cyan transition-colors">
                    {c.label}
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">{c.desc}</p>
                </Link>
              ))}
            </div>
          </section>

          {/* Active investigations */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-300 tracking-wide uppercase">
                Active Investigations
              </h2>
              <Link href="/" className="text-xs text-brand-cyan hover:underline">
                View All →
              </Link>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-12 text-slate-400 text-xs gap-2">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading…
              </div>
            ) : cases.length === 0 ? (
              <div className="bg-brand-panel/80 border border-brand-border rounded-xl p-8 text-center text-xs text-slate-400">
                No authorized cases yet. <Link href="/cases" className="text-brand-cyan hover:underline">Create a Case →</Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {cases.map((c) => (
                  <div
                    key={c.id}
                    className="bg-brand-panel/80 backdrop-blur border border-brand-border hover:border-brand-cyan/40 rounded-xl p-4 transition group"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <span className="font-mono text-brand-cyan text-xs font-semibold">{c.case_code}</span>
                      <StatusBadge status={caseVariant(c.status)} />
                    </div>
                    <h3 className="text-sm font-semibold text-white group-hover:text-brand-cyan transition mb-1">
                      {c.title}
                    </h3>
                    <p className="text-[11px] text-slate-400 mb-3 line-clamp-2">
                      {c.description ?? c.case_type.replace(/_/g, ' ')}
                    </p>
                    <div className="text-[10px] text-slate-500 mb-3">
                      Updated {formatDate(c.updated_at)}
                    </div>
                    <div className="flex gap-2">
                      <Link
                        href={`/cases/${c.id}/evidence`}
                        className="flex-1 text-center py-1.5 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-cyan/40 text-slate-300 rounded transition"
                      >
                        Evidence
                      </Link>
                      <Link
                        href={`/cases/${c.id}/graph`}
                        className="flex-1 text-center py-1.5 text-[11px] font-medium bg-brand-cyan/10 border border-brand-cyan/30 hover:bg-brand-cyan/20 text-brand-cyan rounded transition"
                      >
                        Graph →
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Footer */}
          <footer className="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-brand-border/40 pt-4 pb-2">
            <div className="flex items-center gap-2">
              <span className="text-slate-400">SPYDER-DETECT</span>
              <span className="text-[9px] bg-brand-cyan/10 text-brand-cyan px-1.5 py-0.5 rounded border border-brand-cyan/30">
                SYSTEM ONLINE
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
              SECURE · ANALYSE · EMPOWER
            </div>
          </footer>

        </div>
      </AppShell>
    </>
  )
}
