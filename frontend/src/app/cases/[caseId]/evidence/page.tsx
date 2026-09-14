'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/ToastNotification'
import { casesApi, evidenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case, EvidenceItem, AuditEvent } from '@/types'

function formatBytes(b?: number) {
  if (!b) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1048576).toFixed(1)} MB`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

export default function EvidenceLockerPage() {
  const router  = useRouter()
  const { caseId } = useParams<{ caseId: string }>()
  const { toast }  = useToast()

  const [caseData, setCaseData]       = useState<Case | null>(null)
  const [evidence, setEvidence]       = useState<EvidenceItem[]>([])
  const [loading, setLoading]         = useState(true)
  const [selected, setSelected]       = useState<EvidenceItem | null>(null)
  const [auditLog, setAuditLog]       = useState<AuditEvent[]>([])
  const [showAudit, setShowAudit]     = useState(false)
  const [verifying, setVerifying]     = useState<string | null>(null)
  const [parsing, setParsing]         = useState<string | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    Promise.all([
      casesApi.get(caseId),
      evidenceApi.list(caseId),
    ]).then(([c, e]) => {
      setCaseData(c.data)
      setEvidence(e.data)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [caseId, router])

  const verifyIntegrity = async (evId: string) => {
    setVerifying(evId)
    try {
      const { data } = await evidenceApi.verifyIntegrity(caseId, evId)
      toast(`Integrity check: ${data.status}`, data.match ? 'info' : 'error')
      setEvidence((prev) => prev.map((e) => e.id === evId ? { ...e, integrity_status: data.status } : e))
    } catch {
      toast('Integrity check failed', 'error')
    } finally { setVerifying(null) }
  }

  const triggerParse = async (evId: string) => {
    setParsing(evId)
    try {
      await evidenceApi.parse(caseId, evId)
      toast('Parse job started', 'info')
      setEvidence((prev) => prev.map((e) => e.id === evId ? { ...e, parsing_status: 'PROCESSING' } : e))
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Parse failed'
      toast(msg, 'error')
    } finally { setParsing(null) }
  }

  const openAudit = async (ev: EvidenceItem) => {
    setSelected(ev)
    setShowAudit(true)
    try {
      const { data } = await evidenceApi.audit(caseId, ev.id)
      setAuditLog(data)
    } catch { setAuditLog([]) }
  }

  const integrityColor = (s: string) => {
    if (s === 'VERIFIED')  return 'text-brand-green'
    if (s === 'MISMATCH')  return 'text-brand-red'
    return 'text-slate-400'
  }

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        {/* Header */}
        <section className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-lg bg-brand-surface border border-brand-borderLight flex items-center justify-center font-mono font-semibold text-slate-200 text-sm">
              03
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-wide">Evidence Locker</h1>
              <p className="text-xs text-slate-400">
                {caseData ? `${caseData.case_code} — ${caseData.title}` : 'Loading…'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href={`/cases/${caseId}/graph`}
              className="px-3 py-1.5 text-xs font-medium bg-brand-cyan/15 border border-brand-cyan/40 text-brand-cyan rounded-md hover:bg-brand-cyan/25 transition"
            >
              Open Graph →
            </Link>
            <Link
              href="/import"
              className="px-3 py-1.5 text-xs font-medium bg-brand-surface border border-brand-border text-slate-300 rounded-md hover:border-slate-500 transition"
            >
              + Import Evidence
            </Link>
          </div>
        </section>

        {/* Evidence cards */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-400 text-xs gap-2">
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading evidence…
          </div>
        ) : evidence.length === 0 ? (
          <div className="bg-brand-panel border border-brand-border rounded-xl p-12 text-center">
            <p className="text-slate-400 text-sm">No evidence ingested yet.</p>
            <Link href="/import" className="mt-3 inline-block text-brand-cyan text-xs hover:underline">
              Import Evidence →
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {evidence.map((ev) => (
              <div key={ev.id} className="bg-brand-panel border border-brand-border rounded-xl p-4 hover:border-brand-borderLight transition">
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                  {/* Left: file info */}
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-lg bg-brand-surface border border-brand-border flex items-center justify-center text-brand-cyan flex-shrink-0 font-mono text-[10px] font-bold">
                      {ev.file_extension?.toUpperCase().replace('.', '') ?? 'DOC'}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-brand-cyan text-xs font-semibold">{ev.evidence_code}</span>
                        <span className="text-[10px] text-slate-400">{ev.source_label}</span>
                      </div>
                      <p className="text-sm text-white font-medium mt-0.5">{ev.original_filename}</p>
                      <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
                        <span>{formatBytes(ev.file_size_bytes)}</span>
                        <span>·</span>
                        <span>Uploaded {formatDate(ev.uploaded_at)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Right: badges + actions */}
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <StatusBadge status={ev.integrity_status.toLowerCase().replace('_', '-')} />
                    <StatusBadge status={ev.parsing_status.toLowerCase().replace('_', '-')} />
                  </div>
                </div>

                {/* SHA-256 row */}
                <div className="mt-3 flex items-center gap-2 bg-[#070D14] rounded px-3 py-2 border border-brand-border/60">
                  <span className="text-[10px] font-mono text-slate-500 uppercase">SHA-256</span>
                  <span className="font-mono text-[11px] text-brand-cyan truncate flex-1">{ev.sha256_hash}</span>
                  <button
                    onClick={() => { navigator.clipboard.writeText(ev.sha256_hash); toast('Hash copied', 'info') }}
                    className="text-slate-400 hover:text-white text-[10px] ml-2 flex-shrink-0"
                    title="Copy hash"
                  >
                    📋
                  </button>
                  <span className={`text-[10px] font-mono flex-shrink-0 ${integrityColor(ev.integrity_status)}`}>
                    {ev.integrity_status}
                  </span>
                </div>

                {/* Action buttons */}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={() => verifyIntegrity(ev.id)}
                    disabled={verifying === ev.id}
                    className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-cyan/40 text-brand-cyan rounded transition disabled:opacity-50"
                  >
                    {verifying === ev.id ? 'Verifying…' : 'Verify Integrity'}
                  </button>
                  <button
                    onClick={() => triggerParse(ev.id)}
                    disabled={parsing === ev.id || ev.parsing_status === 'PROCESSING'}
                    className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-amber/40 text-brand-amber rounded transition disabled:opacity-50"
                  >
                    {parsing === ev.id ? 'Queuing…' : 'Parse Evidence'}
                  </button>
                  <button
                    onClick={() => openAudit(ev)}
                    className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-slate-500 text-slate-300 rounded transition"
                  >
                    Audit Trail
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit trail modal */}
      <Modal
        open={showAudit}
        onClose={() => { setShowAudit(false); setAuditLog([]) }}
        title={`Audit Trail — ${selected?.evidence_code}`}
        subtitle={selected?.original_filename}
        maxWidth="max-w-2xl"
        footer={
          <div className="flex justify-end">
            <button onClick={() => setShowAudit(false)} className="px-4 py-1.5 text-xs bg-brand-surface text-slate-300 border border-brand-border rounded hover:bg-brand-panel">
              Close
            </button>
          </div>
        }
      >
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {auditLog.length === 0 ? (
            <p className="text-slate-400 text-xs text-center py-4">No audit events yet.</p>
          ) : (
            auditLog.map((e) => (
              <div key={e.id} className="bg-brand-surface border border-brand-border rounded p-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-brand-cyan text-[11px]">{e.event_type}</span>
                  <span className="text-slate-500 font-mono text-[10px]">{formatDate(e.event_timestamp)}</span>
                </div>
                {e.event_hash && (
                  <div className="font-mono text-[10px] text-slate-500 mt-1 truncate">
                    Hash: {e.event_hash.slice(0, 32)}…
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </Modal>
    </AppShell>
  )
}
