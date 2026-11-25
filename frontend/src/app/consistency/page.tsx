'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/ToastNotification'
import { casesApi, intelligenceApi } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import type { Case, ConsistencyResult } from '@/types'

export default function ConsistencyLabPage() {
  const router = useRouter()
  const { toast } = useToast()

  const [cases, setCases] = useState<Case[]>([])
  const [caseCode, setCaseCode] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [statementText, setStatementText] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [results, setResults] = useState<ConsistencyResult[]>([])

  const [editing, setEditing] = useState<ConsistencyResult | null>(null)
  const [editLocation, setEditLocation] = useState('')
  const [editObject, setEditObject] = useState('')
  const [editNegated, setEditNegated] = useState(false)
  const [editComment, setEditComment] = useState('')

  const loadResults = useCallback(async (targetCode?: string) => {
    try {
      const { data } = await intelligenceApi.listConsistency({
        case_id: targetCode || undefined,
        limit: 50,
      })
      setResults(data.results ?? [])
    } catch {
      setResults([])
    }
  }, [])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    casesApi.list().then(({ data }) => {
      setCases(data)
      if (data.length > 0) {
        setCaseCode(data[0].case_code)
        loadResults(data[0].case_code)
      } else {
        loadResults()
      }
    }).catch(() => { loadResults() })
  }, [loadResults, router])

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!caseCode || statementText.trim().length < 5) {
      toast('Select a case and enter statement text', 'warn')
      return
    }
    setAnalyzing(true)
    try {
      const { data } = await intelligenceApi.analyzeStatement(
        caseCode,
        statementText.trim(),
        subjectId.trim() || undefined
      )
      toast(`Extracted and verified ${data.results.length} claim(s)`, 'info')
      setResults((prev) => [...data.results, ...prev])
    } catch {
      toast('Failed to analyze statement against case evidence', 'error')
    } finally {
      setAnalyzing(false)
    }
  }

  const openEditor = (r: ConsistencyResult) => {
    setEditing(r)
    setEditLocation(r.claim.location_id ?? '')
    setEditObject(r.claim.object_entity_id ?? '')
    setEditNegated(Boolean(r.claim.negated))
    setEditComment('')
  }

  const saveCorrection = async () => {
    if (!editing) return
    try {
      const { data } = await intelligenceApi.correctClaim(editing.result_id, {
        location_id: editLocation || undefined,
        object_entity_id: editObject || undefined,
        negated: editNegated,
        reviewer_comment: editComment || undefined,
      })
      toast(`Claim corrected & re-evaluated: ${data.evaluation.status}`, 'info')
      setEditing(null)
      await loadResults(caseCode)
    } catch {
      toast('Failed to save claim correction', 'error')
    }
  }

  const statusStyle = (s: string) => {
    if (s === 'SUPPORTED') return 'bg-brand-green/15 text-brand-green border-brand-green/40'
    if (s === 'CONTRADICTED') return 'bg-brand-red/15 text-brand-red border-brand-red/40'
    if (s === 'EVIDENCE_CONFLICT') return 'bg-brand-amber/15 text-brand-amber border-brand-amber/40'
    return 'bg-slate-800 text-slate-300 border-slate-700'
  }

  return (
    <AppShell>
      <div className="px-6 py-5 space-y-5 bg-brand-bg min-h-full">
        <section className="border-b border-brand-border/40 pb-4">
          <h1 className="text-xl font-bold text-white tracking-tight">Statement-Evidence Consistency Lab</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Extract structured claims from witness/suspect statements, inspect contradictions, and manually correct claims without overwriting originals.
          </p>
        </section>

        {/* Submit Statement */}
        <section className="bg-brand-panel border border-brand-border rounded-xl p-5">
          <form onSubmit={handleAnalyze} className="space-y-3 text-xs">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-[11px] font-mono text-slate-400 block mb-1">Case Dossier</label>
                <select
                  value={caseCode}
                  onChange={(e) => { setCaseCode(e.target.value); loadResults(e.target.value) }}
                  className="w-full bg-[#070D14] border border-brand-border rounded px-3 py-2 text-slate-100"
                >
                  {cases.map((c) => (
                    <option key={c.id} value={c.case_code}>{c.case_code} — {c.title}</option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="text-[11px] font-mono text-slate-400 block mb-1">Attributed Subject Person ID (Optional)</label>
                <input
                  value={subjectId}
                  onChange={(e) => setSubjectId(e.target.value)}
                  placeholder="e.g. CASE_001_PER_01"
                  className="w-full bg-[#070D14] border border-brand-border rounded px-3 py-2 text-slate-100"
                />
              </div>
            </div>
            <div>
              <label className="text-[11px] font-mono text-slate-400 block mb-1">Statement Narrative</label>
              <textarea
                value={statementText}
                onChange={(e) => setStatementText(e.target.value)}
                rows={3}
                placeholder='e.g. "I was not in Kolkata on 2025-07-10 and never called +919876543210."'
                className="w-full bg-[#070D14] border border-brand-border rounded p-3 text-slate-100"
              />
            </div>
            <button
              type="submit"
              disabled={analyzing}
              className="px-4 py-2 bg-brand-cyan hover:bg-brand-cyan/80 text-black font-semibold rounded transition disabled:opacity-50"
            >
              {analyzing ? 'Analyzing Claims…' : 'Analyze Against Case Evidence'}
            </button>
          </form>
        </section>

        {/* Results */}
        <section className="space-y-3">
          {results.length === 0 ? (
            <div className="bg-brand-panel border border-brand-border rounded-xl p-10 text-center text-xs text-slate-400">
              No consistency evaluations recorded for this case yet.
            </div>
          ) : results.map((r) => (
            <div key={r.result_id} className="bg-brand-panel border border-brand-border rounded-xl p-4 space-y-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 font-mono">
                  <span className={`px-2 py-0.5 rounded border text-[11px] font-bold ${statusStyle(r.status)}`}>
                    {r.status}
                  </span>
                  <span className="text-brand-cyan">{r.claim.predicate}</span>
                  {r.claim.negated && <span className="text-brand-red">(NEGATED)</span>}
                  {r.claim.location_id && <span className="text-slate-300">@ {r.claim.location_id}</span>}
                </div>
                <button
                  onClick={() => openEditor(r)}
                  className="px-2.5 py-1 rounded bg-brand-surface border border-brand-border hover:border-brand-cyan text-brand-cyan text-[11px]"
                >
                  Correct Extracted Claim
                </button>
              </div>
              <p className="text-slate-200 italic">&ldquo;{r.claim.raw_text}&rdquo;</p>
              <p className="text-slate-300">{r.explanation}</p>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 bg-[#070D14] border border-brand-border rounded p-2.5 font-mono text-[10px]">
                <div>Overall: <span className="text-brand-cyan">{(r.confidence.overall_confidence * 100).toFixed(0)}%</span></div>
                <div>Specificity: {(r.confidence.statement_specificity * 100).toFixed(0)}%</div>
                <div>Coverage: {(r.confidence.evidence_coverage * 100).toFixed(0)}%</div>
                <div>Corroboration: {(r.confidence.corroboration_strength * 100).toFixed(0)}%</div>
                <div>Contradiction: {(r.confidence.contradiction_strength * 100).toFixed(0)}%</div>
              </div>
            </div>
          ))}
        </section>
      </div>

      {editing && (
        <Modal
          open={!!editing}
          onClose={() => setEditing(null)}
          title="Correct Extracted Claim"
          subtitle="Original LLM/rule extraction stays preserved in audit history."
          footer={
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditing(null)} className="px-3 py-1.5 text-xs bg-brand-surface text-slate-300 border border-brand-border rounded">Cancel</button>
              <button onClick={saveCorrection} className="px-3 py-1.5 text-xs bg-brand-cyan text-black font-semibold rounded">Re-Evaluate &amp; Save</button>
            </div>
          }
        >
          <div className="space-y-3 text-xs">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Location ID</label>
              <input value={editLocation} onChange={(e) => setEditLocation(e.target.value)} className="w-full bg-[#070D14] border border-brand-border rounded px-2.5 py-1.5 text-slate-100" />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Object Entity ID</label>
              <input value={editObject} onChange={(e) => setEditObject(e.target.value)} className="w-full bg-[#070D14] border border-brand-border rounded px-2.5 py-1.5 text-slate-100" />
            </div>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={editNegated} onChange={(e) => setEditNegated(e.target.checked)} />
              <span className="text-slate-200">Statement denies / negates this claim</span>
            </label>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Investigator Comment</label>
              <input value={editComment} onChange={(e) => setEditComment(e.target.value)} placeholder="Why claim extraction was adjusted..." className="w-full bg-[#070D14] border border-brand-border rounded px-2.5 py-1.5 text-slate-100" />
            </div>
          </div>
        </Modal>
      )}
    </AppShell>
  )
}
