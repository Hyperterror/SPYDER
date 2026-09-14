'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import StatusBadge from '@/components/ui/StatusBadge'
import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/ToastNotification'
import { casesApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case } from '@/types'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { dateStyle: 'medium' })
}
function caseVariant(status: string) {
  const m: Record<string, string> = { ACTIVE: 'in-progress', ON_HOLD: 'under-review', CLOSED: 'closed', DRAFT: 'draft' }
  return m[status] ?? 'active'
}

export default function CasesPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [cases, setCases]     = useState<Case[]>([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [title, setTitle]     = useState('')
  const [type, setType]       = useState('HUMAN_TRAFFICKING')
  const [desc, setDesc]       = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    casesApi.list().then(({ data }) => setCases(data)).catch(() => {}).finally(() => setLoading(false))
  }, [router])

  const createCase = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const { data } = await casesApi.create({ title, case_type: type, description: desc })
      setCases((prev) => [data, ...prev])
      toast(`Case ${data.case_code} created`, 'info')
      setShowNew(false); setTitle(''); setDesc('')
    } catch { toast('Failed to create case', 'error') }
    finally { setCreating(false) }
  }

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <section className="flex items-center justify-between border-b border-brand-border/40 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Cases</h1>
            <p className="text-xs text-slate-400 mt-0.5">All investigations in your docket</p>
          </div>
          <button
            onClick={() => setShowNew(true)}
            className="px-4 py-2 bg-brand-cyan/15 hover:bg-brand-cyan/25 border border-brand-cyan/50 text-brand-cyan rounded-md text-xs font-semibold transition active:scale-95"
          >
            + New Case
          </button>
        </section>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-400 text-xs gap-2">
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading cases…
          </div>
        ) : (
          <div className="bg-brand-panel border border-brand-border rounded-lg overflow-hidden">
            <table className="w-full text-left text-xs text-slate-300">
              <thead>
                <tr className="border-b border-brand-border text-[11px] font-mono uppercase text-slate-400">
                  <th className="px-4 py-3">Case ID</th>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/40">
                {cases.map((c) => (
                  <tr key={c.id} className="hover:bg-brand-surface/70 transition">
                    <td className="px-4 py-3 font-mono text-brand-cyan font-semibold">{c.case_code}</td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-white">{c.title}</div>
                      {c.description && <div className="text-[11px] text-slate-500 truncate max-w-xs">{c.description}</div>}
                    </td>
                    <td className="px-4 py-3 text-slate-400">{c.case_type.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3"><StatusBadge status={caseVariant(c.status)} /></td>
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-400">{formatDate(c.updated_at)}</td>
                    <td className="px-4 py-3 text-right flex items-center justify-end gap-2">
                      <Link href={`/cases/${c.id}/evidence`} className="text-[11px] text-slate-400 hover:text-brand-cyan transition">
                        Evidence
                      </Link>
                      <Link href={`/cases/${c.id}/graph`} className="text-[11px] text-brand-cyan hover:underline transition">
                        Graph →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cases.length === 0 && (
              <div className="text-center py-12 text-slate-400 text-xs">
                No cases yet. <button onClick={() => setShowNew(true)} className="text-brand-cyan hover:underline">Create the first one →</button>
              </div>
            )}
          </div>
        )}
      </div>

      <Modal
        open={showNew}
        onClose={() => setShowNew(false)}
        title="New Investigation Case"
        subtitle="Fill in case details to open a new docket"
        footer={
          <div className="flex items-center justify-end gap-3">
            <button onClick={() => setShowNew(false)} className="text-xs text-slate-400 hover:text-white">Cancel</button>
            <button
              form="new-case-form"
              type="submit"
              disabled={creating}
              className="px-4 py-1.5 text-xs bg-brand-cyan hover:bg-brand-cyan/80 text-black font-semibold rounded disabled:opacity-50"
            >
              {creating ? 'Creating…' : 'Create Case'}
            </button>
          </div>
        }
      >
        <form id="new-case-form" onSubmit={createCase} className="space-y-4 text-xs">
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Case Title *</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required
              className="w-full bg-[#0B131E] border border-brand-border rounded px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-brand-cyan" />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Case Type</label>
            <select value={type} onChange={(e) => setType(e.target.value)}
              className="w-full bg-[#0B131E] border border-brand-border rounded px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-brand-cyan">
              <option value="HUMAN_TRAFFICKING">Human Trafficking</option>
              <option value="CYBER_CRIME">Cyber Crime</option>
              <option value="FINANCIAL_CRIME">Financial Crime</option>
              <option value="ORGANIZED_CRIME">Organized Crime</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Description</label>
            <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3}
              className="w-full bg-[#0B131E] border border-brand-border rounded px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-brand-cyan resize-none" />
          </div>
        </form>
      </Modal>
    </AppShell>
  )
}
