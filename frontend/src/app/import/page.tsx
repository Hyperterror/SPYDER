'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import { useToast } from '@/components/ui/ToastNotification'
import { casesApi, evidenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case, EvidenceItem } from '@/types'

interface UploadFile {
  id: string
  file: File
  progress: number
  status: 'queued' | 'uploading' | 'done' | 'error'
  evidenceItem?: EvidenceItem
  error?: string
}

export default function ImportPage() {
  const router = useRouter()
  const { toast } = useToast()
  const dropRef  = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const [cases, setCases]         = useState<Case[]>([])
  const [caseId, setCaseId]       = useState('')
  const [dragging, setDragging]   = useState(false)
  const [uploads, setUploads]     = useState<UploadFile[]>([])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    casesApi.list().then(({ data }) => {
      setCases(data)
      if (data.length > 0) setCaseId(data[0].id)
    }).catch(() => {})
  }, [router])

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files || !caseId) return
    const allowed = ['.csv', '.xlsx', '.json']
    Array.from(files).forEach((file) => {
      const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
      if (!allowed.includes(ext)) {
        toast(`Unsupported file type: ${ext}`, 'error')
        return
      }
      const id = Math.random().toString(36).slice(2)
      setUploads((prev) => [...prev, { id, file, progress: 0, status: 'queued' }])
      uploadFile(id, file)
    })
  }, [caseId]) // eslint-disable-line react-hooks/exhaustive-deps

  const uploadFile = async (id: string, file: File) => {
    setUploads((prev) => prev.map((u) => u.id === id ? { ...u, status: 'uploading', progress: 30 } : u))
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('source_label', file.name.includes('cdr') ? 'CDR' : file.name.includes('transaction') || file.name.includes('upi') ? 'UPI Transactions' : 'Evidence')
      const { data } = await evidenceApi.upload(caseId, fd)
      setUploads((prev) => prev.map((u) => u.id === id
        ? { ...u, status: 'done', progress: 100, evidenceItem: data }
        : u
      ))
      toast(`${file.name} uploaded — SHA-256 verified`, 'info')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Upload failed'
      setUploads((prev) => prev.map((u) => u.id === id ? { ...u, status: 'error', progress: 0, error: msg } : u))
      toast(msg, 'error')
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const CAPABILITY_CARDS = [
    { icon: '📄', title: 'Multiple Formats', desc: 'CSV, XLSX, JSON supported' },
    { icon: '🔐', title: 'SHA-256 Auto-Hash', desc: 'Cryptographic fingerprint on upload' },
    { icon: '⛓️', title: 'Chain of Custody', desc: 'Immutable audit trail per file' },
    { icon: '⚡', title: 'Parse Engine', desc: 'CDR & transaction auto-parsing' },
  ]

  return (
    <AppShell>
      <div className="px-6 lg:px-7 py-5 space-y-6 bg-brand-bg min-h-full">
        {/* Header */}
        <section className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg border border-brand-border bg-brand-surface flex items-center justify-center font-semibold text-slate-300 text-sm">
              02
            </div>
            <div>
              <h1 className="text-xl lg:text-2xl font-semibold text-white tracking-tight">Import Evidence</h1>
              <p className="text-xs text-slate-400">Upload and process data from multiple sources</p>
            </div>
          </div>

          {/* Case selector */}
          <select
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            className="bg-brand-surface border border-brand-border text-xs text-slate-200 rounded-md px-3 py-2 focus:outline-none focus:border-brand-cyan"
          >
            {cases.map((c) => (
              <option key={c.id} value={c.id}>{c.case_code} — {c.title}</option>
            ))}
          </select>
        </section>

        {/* Drop zone + capability cards */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
          {/* Drop zone */}
          <div
            ref={dropRef}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`lg:col-span-8 bg-brand-surface/80 border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center transition duration-200 relative group cursor-pointer ${
              dragging ? 'dropzone-active' : 'border-brand-borderLight hover:border-brand-cyan/60'
            }`}
          >
            <input ref={inputRef} type="file" multiple accept=".csv,.xlsx,.json" className="hidden" onChange={(e) => handleFiles(e.target.files)} />

            <div className="w-16 h-16 rounded-full bg-[#0E2235]/70 border border-brand-borderLight flex items-center justify-center mb-4 group-hover:scale-105 transition">
              <svg className="w-8 h-8 text-brand-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M12 12v9m-4-4l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
              </svg>
            </div>
            <h2 className="text-base lg:text-lg font-medium text-white mb-1">Drag &amp; drop files here</h2>
            <p className="text-xs text-slate-400 mb-5">or</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}
              className="bg-brand-cyan hover:bg-brand-cyanDim text-black text-xs font-semibold px-6 py-2.5 rounded-lg shadow-lg transition active:scale-95"
            >
              Browse Files
            </button>
            <div className="mt-7 text-center">
              <p className="text-[11px] text-slate-400 mb-1.5">Supported formats: CSV, XLSX, JSON</p>
              <p className="text-[11px] text-slate-400">CDR Records • Bank Statements • UPI Transactions</p>
            </div>

            {dragging && (
              <div className="absolute inset-0 bg-brand-surface/95 rounded-xl border-2 border-brand-cyan flex flex-col items-center justify-center backdrop-blur-sm z-10">
                <svg className="w-12 h-12 text-brand-cyan animate-bounce mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M12 12v9m-4-4l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                </svg>
                <p className="text-white font-medium text-sm">Release to initiate ingestion</p>
              </div>
            )}
          </div>

          {/* Capability cards */}
          <div className="lg:col-span-4 flex flex-col justify-between gap-3">
            {CAPABILITY_CARDS.map((c) => (
              <div key={c.title} className="bg-brand-surface/60 border border-brand-border rounded-xl p-3.5 flex items-start gap-3.5 hover:border-slate-700 transition">
                <div className="w-9 h-9 rounded-lg bg-brand-panel border border-brand-borderLight flex items-center justify-center flex-shrink-0 text-brand-cyan text-lg">
                  {c.icon}
                </div>
                <div>
                  <h3 className="text-xs font-semibold text-white">{c.title}</h3>
                  <p className="text-[11px] text-slate-400 leading-snug mt-0.5">{c.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Upload queue */}
        {uploads.length > 0 && (
          <section className="bg-brand-surface border border-brand-border rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-brand-border flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-white">Upload Queue ({uploads.length})</h2>
                <p className="text-[11px] text-slate-400">Files are securely processed and stored.</p>
              </div>
              <button
                onClick={() => setUploads([])}
                className="text-xs text-slate-400 hover:text-brand-red transition"
              >
                Clear All
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="text-slate-400 border-b border-brand-border text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-5">File Name</th>
                    <th className="py-3 px-5">SHA-256</th>
                    <th className="py-3 px-5">Status</th>
                    <th className="py-3 px-5">Progress</th>
                    <th className="py-3 px-5">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-brand-border/50">
                  {uploads.map((u) => (
                    <tr key={u.id} className="hover:bg-brand-panel transition">
                      <td className="py-3 px-5 font-mono text-slate-200">{u.file.name}</td>
                      <td className="py-3 px-5 font-mono text-[10px] text-slate-400 max-w-[180px] truncate">
                        {u.evidenceItem?.sha256_hash
                          ? u.evidenceItem.sha256_hash.slice(0, 16) + '…'
                          : '—'
                        }
                      </td>
                      <td className="py-3 px-5">
                        <StatusBadge status={u.status === 'done' ? 'completed' : u.status === 'uploading' ? 'processing' : u.status === 'error' ? 'failed' : 'pending'} />
                      </td>
                      <td className="py-3 px-5 w-40">
                        <div className="progress-bar-track h-1.5 w-full">
                          <div className="progress-bar-fill" style={{ width: `${u.progress}%` }} />
                        </div>
                      </td>
                      <td className="py-3 px-5">
                        {u.evidenceItem && (
                          <button
                            onClick={() => evidenceApi.parse(caseId, u.evidenceItem!.id).then(() => toast(`Parse job started for ${u.file.name}`))}
                            className="text-[11px] text-brand-cyan hover:underline"
                          >
                            Parse
                          </button>
                        )}
                        {u.status === 'error' && (
                          <span className="text-[11px] text-brand-red">{u.error}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </AppShell>
  )
}
