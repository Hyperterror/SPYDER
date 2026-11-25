'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/ToastNotification'
import { auditApi, casesApi, evidenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case, EvidenceItem, AuditEvent, AuditChainVerification } from '@/types'

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
  const router = useRouter()
  const { caseId } = useParams<{ caseId: string }>()
  const { toast } = useToast()

  const [caseData, setCaseData] = useState<Case | null>(null)
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [chainCheck, setChainCheck] = useState<AuditChainVerification | null>(null)
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState<EvidenceItem | null>(null)
  const [auditLog, setAuditLog] = useState<AuditEvent[]>([])
  const [showAudit, setShowAudit] = useState(false)
  const [showTextModal, setShowTextModal] = useState(false)

  const [withdrawTarget, setWithdrawTarget] = useState<EvidenceItem | null>(null)
  const [withdrawReason, setWithdrawReason] = useState('')
  const [supersedeTarget, setSupersedeTarget] = useState<EvidenceItem | null>(null)
  const [supersedeFile, setSupersedeFile] = useState<File | null>(null)
  const [supersedeReason, setSupersedeReason] = useState('')

  const [verifying, setVerifying] = useState<string | null>(null)
  const [processingId, setProcessingId] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    try {
      const [cRes, eRes, chRes] = await Promise.all([
        casesApi.get(caseId),
        evidenceApi.list(caseId),
        auditApi.verifyChain(caseId).catch(() => ({ data: null })),
      ])
      setCaseData(cRes.data)
      setEvidence(eRes.data)
      if (chRes.data) setChainCheck(chRes.data)
    } catch {
      toast('Failed to load evidence locker', 'error')
    } finally {
      setLoading(false)
    }
  }, [caseId, toast])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    loadAll()
  }, [loadAll, router])

  const verifyIntegrity = async (evId: string) => {
    setVerifying(evId)
    try {
      const { data } = await evidenceApi.verifyIntegrity(caseId, evId)
      toast(`Integrity check: ${data.status}`, data.match ? 'info' : 'error')
      setEvidence((prev) => prev.map((e) => (e.id === evId ? { ...e, integrity_status: data.status } : e)))
    } catch {
      toast('Integrity check failed', 'error')
    } finally {
      setVerifying(null)
    }
  }

  const triggerProcess = async (evId: string, isRetry = false) => {
    setProcessingId(evId)
    try {
      const { data } = isRetry
        ? await evidenceApi.retry(caseId, evId, true)
        : await evidenceApi.process(caseId, evId, true)
      toast(`Pipeline ${data.status} (${data.records_processed ?? 0} valid records)`, data.status === 'FAILED' ? 'error' : 'info')
      await loadAll()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Processing failed'
      toast(msg, 'error')
    } finally {
      setProcessingId(null)
    }
  }

  const cancelJob = async (evId: string) => {
    try {
      await evidenceApi.cancel(caseId, evId)
      toast('Processing job cancelled', 'warn')
      await loadAll()
    } catch {
      toast('Job could not be cancelled in its current state', 'warn')
    }
  }

  const downloadOriginal = async (ev: EvidenceItem) => {
    try {
      const res = await evidenceApi.download(caseId, ev.id)
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = ev.sanitized_filename || ev.original_filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast('Failed to download original file', 'error')
    }
  }

  const submitWithdraw = async () => {
    if (!withdrawTarget || withdrawReason.trim().length < 5) {
      toast('Provide a withdrawal rationale (min 5 characters)', 'warn')
      return
    }
    try {
      await evidenceApi.withdraw(caseId, withdrawTarget.id, withdrawReason.trim())
      toast('Evidence withdrawn (original bytes and audit retained)', 'info')
      setWithdrawTarget(null)
      setWithdrawReason('')
      await loadAll()
    } catch {
      toast('Withdrawal failed or not permitted', 'error')
    }
  }

  const submitSupersede = async () => {
    if (!supersedeTarget || !supersedeFile) {
      toast('Select a replacement file', 'warn')
      return
    }
    try {
      const fd = new FormData()
      fd.append('file', supersedeFile)
      if (supersedeReason.trim()) fd.append('reason', supersedeReason.trim())
      await evidenceApi.supersede(caseId, supersedeTarget.id, fd)
      toast('New evidence version registered; original preserved', 'info')
      setSupersedeTarget(null)
      setSupersedeFile(null)
      setSupersedeReason('')
      await loadAll()
    } catch {
      toast('Supersede failed', 'error')
    }
  }

  const openAudit = async (ev: EvidenceItem) => {
    setSelected(ev)
    setShowAudit(true)
    try {
      const { data } = await evidenceApi.audit(caseId, ev.id)
      setAuditLog(data)
    } catch {
      setAuditLog([])
    }
  }

  const integrityColor = (s: string) => {
    if (s === 'VERIFIED') return 'text-brand-green'
    if (s === 'MISMATCH') return 'text-brand-red'
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
          <div className="flex flex-wrap items-center gap-2.5">
            {chainCheck && (
              <span
                className={`px-2.5 py-1 rounded text-[11px] font-mono border ${
                  chainCheck.is_valid
                    ? 'bg-brand-green/10 border-brand-green/30 text-brand-green'
                    : 'bg-brand-red/10 border-brand-red/40 text-brand-red'
                }`}
              >
                {chainCheck.is_valid
                  ? `Chain Sealed (${chainCheck.total_events} events)`
                  : `TAMPER ALERT: ${chainCheck.reason || 'Hash mismatch'}`}
              </span>
            )}
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
            {evidence.map((ev) => {
              const lifecycle = ev.lifecycle_status ?? 'ACTIVE'
              return (
                <div
                  key={ev.id}
                  className={`bg-brand-panel border rounded-xl p-4 transition ${
                    lifecycle === 'ACTIVE'
                      ? 'border-brand-border hover:border-brand-borderLight'
                      : 'border-brand-amber/30 opacity-85'
                  }`}
                >
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-lg bg-brand-surface border border-brand-border flex items-center justify-center text-brand-cyan flex-shrink-0 font-mono text-[10px] font-bold">
                        {ev.file_extension?.toUpperCase().replace('.', '') ?? 'DOC'}
                      </div>
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-brand-cyan text-xs font-semibold">{ev.evidence_code}</span>
                          <span className="px-1.5 py-0.5 rounded bg-brand-surface border border-brand-border font-mono text-[10px] text-slate-300">
                            v{ev.version_number ?? 1}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded font-mono text-[10px] border ${
                              lifecycle === 'ACTIVE'
                                ? 'bg-brand-green/10 text-brand-green border-brand-green/30'
                                : lifecycle === 'WITHDRAWN'
                                ? 'bg-brand-red/10 text-brand-red border-brand-red/30'
                                : 'bg-brand-amber/10 text-brand-amber border-brand-amber/30'
                            }`}
                          >
                            {lifecycle}
                          </span>
                          <span className="text-[10px] text-slate-400">{ev.source_label}</span>
                        </div>
                        <p className="text-sm text-white font-medium mt-0.5">{ev.original_filename}</p>
                        <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
                          <span>{formatBytes(ev.file_size_bytes)}</span>
                          <span>·</span>
                          <span>Uploaded {formatDate(ev.uploaded_at)}</span>
                        </div>
                        {ev.withdrawn_reason && (
                          <p className="text-[11px] text-brand-red mt-1">
                            Withdrawn reason: {ev.withdrawn_reason}
                          </p>
                        )}
                      </div>
                    </div>

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
                      Copy
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
                      onClick={() => triggerProcess(ev.id, ev.parsing_status === 'FAILED')}
                      disabled={processingId === ev.id || lifecycle !== 'ACTIVE'}
                      className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-amber/40 text-brand-amber rounded transition disabled:opacity-50"
                    >
                      {processingId === ev.id
                        ? 'Processing…'
                        : ev.parsing_status === 'FAILED'
                        ? 'Retry Pipeline'
                        : 'Run Canonical Pipeline'}
                    </button>
                    {ev.parsing_status === 'PROCESSING' && (
                      <button
                        onClick={() => cancelJob(ev.id)}
                        className="px-2.5 py-1 text-[11px] font-medium bg-brand-red/10 border border-brand-red/40 text-brand-red rounded"
                      >
                        Cancel Job
                      </button>
                    )}
                    <button
                      onClick={() => downloadOriginal(ev)}
                      className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-slate-500 text-slate-200 rounded transition"
                    >
                      Download Original
                    </button>
                    {ev.extracted_text && (
                      <button
                        onClick={() => { setSelected(ev); setShowTextModal(true) }}
                        className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-purple/40 text-brand-purple rounded transition"
                      >
                        Extracted Text
                      </button>
                    )}
                    {lifecycle === 'ACTIVE' && (
                      <>
                        <button
                          onClick={() => setSupersedeTarget(ev)}
                          className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-cyan/40 text-slate-300 rounded transition"
                        >
                          Supersede
                        </button>
                        <button
                          onClick={() => setWithdrawTarget(ev)}
                          className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-brand-red/40 text-brand-red rounded transition"
                        >
                          Withdraw
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => openAudit(ev)}
                      className="px-2.5 py-1 text-[11px] font-medium bg-brand-surface border border-brand-border hover:border-slate-500 text-slate-300 rounded transition"
                    >
                      Audit Trail
                    </button>
                  </div>
                </div>
              )
            })}
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

      {/* Extracted text modal */}
      <Modal
        open={showTextModal}
        onClose={() => setShowTextModal(false)}
        title={`Extracted Document Text — ${selected?.evidence_code}`}
        subtitle={selected?.original_filename}
        maxWidth="max-w-2xl"
        footer={
          <div className="flex justify-end">
            <button onClick={() => setShowTextModal(false)} className="px-4 py-1.5 text-xs bg-brand-surface text-slate-300 border border-brand-border rounded">
              Close
            </button>
          </div>
        }
      >
        <pre className="bg-[#070D14] border border-brand-border rounded p-3 text-xs text-slate-200 font-mono whitespace-pre-wrap max-h-96 overflow-y-auto">
          {selected?.extracted_text || 'No extracted text recorded.'}
        </pre>
      </Modal>

      {/* Withdraw modal */}
      <Modal
        open={!!withdrawTarget}
        onClose={() => { setWithdrawTarget(null); setWithdrawReason('') }}
        title={`Withdraw Evidence — ${withdrawTarget?.evidence_code}`}
        subtitle="Original bytes and audit history are preserved immutably."
        footer={
          <div className="flex justify-end gap-2">
            <button onClick={() => setWithdrawTarget(null)} className="px-3 py-1.5 text-xs bg-brand-surface text-slate-300 border border-brand-border rounded">Cancel</button>
            <button onClick={submitWithdraw} className="px-3 py-1.5 text-xs bg-brand-red text-white font-semibold rounded">Confirm Withdrawal</button>
          </div>
        }
      >
        <textarea
          value={withdrawReason}
          onChange={(e) => setWithdrawReason(e.target.value)}
          rows={3}
          placeholder="Document legal/evidentiary rationale for withdrawing this item..."
          className="w-full bg-[#070D14] border border-brand-border rounded p-2.5 text-xs text-slate-100 focus:outline-none focus:border-brand-red"
        />
      </Modal>

      {/* Supersede modal */}
      <Modal
        open={!!supersedeTarget}
        onClose={() => { setSupersedeTarget(null); setSupersedeFile(null); setSupersedeReason('') }}
        title={`Supersede Evidence — ${supersedeTarget?.evidence_code}`}
        subtitle="Registers a new version while keeping the original file immutable."
        footer={
          <div className="flex justify-end gap-2">
            <button onClick={() => setSupersedeTarget(null)} className="px-3 py-1.5 text-xs bg-brand-surface text-slate-300 border border-brand-border rounded">Cancel</button>
            <button onClick={submitSupersede} className="px-3 py-1.5 text-xs bg-brand-cyan text-black font-semibold rounded">Upload Version</button>
          </div>
        }
      >
        <div className="space-y-3 text-xs">
          <input
            type="file"
            onChange={(e) => setSupersedeFile(e.target.files?.[0] ?? null)}
            className="block w-full text-slate-300 text-xs"
          />
          <input
            value={supersedeReason}
            onChange={(e) => setSupersedeReason(e.target.value)}
            placeholder="Correction / revision notes..."
            className="w-full bg-[#070D14] border border-brand-border rounded p-2 text-xs text-slate-100"
          />
        </div>
      </Modal>
    </AppShell>
  )
}
