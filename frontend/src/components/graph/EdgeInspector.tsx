'use client'

import type { InvestigationLead } from '@/types'

interface EdgeData {
  edge_id: string
  relationship_type: string
  source: { labels: string[]; normalized_number?: string; normalized_identifier?: string }
  target: { labels: string[]; normalized_number?: string; normalized_identifier?: string }
  event?: {
    timestamp_utc?: string
    duration_seconds?: number
    amount?: number
    currency?: string
    transaction_id?: string
    transaction_type?: string
  }
  provenance?: {
    evidence_id?: string
    source_file_name?: string
    source_row_number?: number
    source_hash?: string
    verification_status?: string
    relationship_status?: string
    confidence_label?: string
  }
  limitations?: string[]
  is_candidate?: boolean
  candidate_lead?: InvestigationLead
}

interface EdgeInspectorProps {
  edge: EdgeData | null
  onClose: () => void
}

export default function EdgeInspector({ edge, onClose }: EdgeInspectorProps) {
  if (!edge) return null

  // ── Render AI Investigative Lead / Potential Association Inspector ────────
  if (edge.is_candidate && edge.candidate_lead) {
    const lead = edge.candidate_lead
    const priorityColor =
      lead.priority === 'HIGH' ? 'text-brand-red bg-brand-red/15 border-brand-red/30' :
      lead.priority === 'REVIEW' ? 'text-brand-amber bg-brand-amber/15 border-brand-amber/30' :
      'text-brand-cyan bg-brand-cyan/15 border-brand-cyan/30'

    return (
      <div className="absolute top-4 right-4 z-30 w-84 sm:w-96 bg-brand-panel/95 border border-purple-500/40 backdrop-blur-md rounded-xl shadow-2xl text-xs overflow-y-auto max-h-[85vh]">
        {/* Header */}
        <div className="px-3.5 py-3 border-b border-brand-border flex items-center justify-between bg-purple-950/20">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              {lead.prediction_type}
            </span>
            <span className="text-purple-200 text-xs font-semibold">AI Lead Details</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">×</button>
        </div>

        {/* Warning Banner */}
        <div className="px-3.5 py-2 bg-amber-500/10 border-b border-amber-500/20 text-[10px] text-amber-300 flex items-center gap-1.5 font-mono">
          <span>⚠</span>
          <span>Investigative Lead — Requires verification. Not proof of guilt.</span>
        </div>

        <div className="p-3.5 space-y-3.5">
          {/* Source ↔ Target */}
          <div className="flex items-center gap-2 bg-[#070D14] rounded border border-purple-500/30 px-3 py-2">
            <span className="font-mono text-brand-cyan text-[11px] truncate flex-1 font-semibold">{lead.source_entity}</span>
            <svg className="w-4 h-4 text-purple-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
            <span className="font-mono text-purple-300 text-[11px] truncate flex-1 text-right font-semibold">{lead.target_entity}</span>
          </div>

          {/* Model Investigation Metrics */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-[#070D14] rounded border border-brand-border p-2">
              <div className="text-[10px] text-slate-400 uppercase font-mono">Investigation Score</div>
              <div className="text-sm font-bold text-white font-mono mt-0.5">
                {(lead.confidence * 100).toFixed(1)}%
              </div>
              <div className="text-[9px] text-slate-500 font-mono">Raw: {lead.confidence.toFixed(3)}</div>
            </div>
            <div className="bg-[#070D14] rounded border border-brand-border p-2">
              <div className="text-[10px] text-slate-400 uppercase font-mono">Priority Tier</div>
              <span className={`inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${priorityColor}`}>
                {lead.priority}
              </span>
            </div>
          </div>

          {/* Scope & Corroboration */}
          <div className="space-y-1 bg-[#070D14] rounded border border-brand-border p-2.5">
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">Lead Scope</span>
              <span className="text-slate-300 font-mono text-[11px]">
                {lead.is_cross_case ? 'Cross-Case Lead' : 'Within-Case Lead'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">Evidence Strength</span>
              <span className="text-brand-green font-mono text-[11px]">{lead.evidence_strength}</span>
            </div>
            {lead.source_case_ids.length > 0 && (
              <div className="flex justify-between">
                <span className="text-slate-500 text-[11px]">Associated Cases</span>
                <span className="text-brand-cyan font-mono text-[11px]">
                  {Array.from(new Set([...lead.source_case_ids, ...lead.target_case_ids])).join(', ')}
                </span>
              </div>
            )}
          </div>

          {/* Why Suggested (Explanation) */}
          <div className="bg-[#070D14] rounded border border-brand-border p-2.5 space-y-1">
            <div className="text-[10px] text-purple-400 uppercase font-mono font-semibold">Why Was This Suggested?</div>
            <p className="text-[11px] text-slate-300 leading-relaxed">{lead.explanation}</p>
          </div>

          {/* Supporting Modalities */}
          {lead.supporting_modalities.length > 0 && (
            <div>
              <div className="text-[10px] text-slate-500 uppercase font-mono mb-1.5">Supporting Modalities</div>
              <div className="flex flex-wrap gap-1.5">
                {lead.supporting_modalities.map((mod, idx) => (
                  <span key={idx} className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/10 text-purple-300 border border-purple-500/20">
                    {mod.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Common Intermediate Entities */}
          {lead.common_intermediates.length > 0 && (
            <div className="bg-[#070D14] rounded border border-brand-border p-2.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500 uppercase font-mono">2-Hop Intermediates</span>
                <span className="text-[10px] font-mono text-purple-300">{lead.common_intermediates_count} total</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {lead.common_intermediates.slice(0, 4).map((item, idx) => (
                  <span key={idx} className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-brand-surface text-slate-300 border border-brand-border">
                    {item}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Caveats & Hard-Negative Safeguards */}
          {lead.caveats.length > 0 && (
            <div className="border border-amber-500/30 rounded p-2.5 bg-amber-500/10 space-y-1">
              <div className="text-[10px] text-amber-300 font-semibold uppercase font-mono">⚠ Evidentiary Caveats</div>
              {lead.caveats.map((cav, idx) => (
                <p key={idx} className="text-[10px] text-amber-200/90 leading-relaxed">• {cav}</p>
              ))}
            </div>
          )}

          {/* Supporting Evidence Records (Provenance) */}
          {lead.supporting_records && lead.supporting_records.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[10px] text-slate-500 uppercase font-mono">Concrete Provenance Records</div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {lead.supporting_records.map((rec, idx) => (
                  <div key={idx} className="bg-[#070D14] border border-brand-border rounded p-2 text-[10px] space-y-0.5">
                    <div className="text-white font-medium">{rec.reason}</div>
                    <div className="flex items-center justify-between text-slate-400 font-mono text-[9px] pt-1 border-t border-brand-border/40">
                      <span>Type: {rec.evidence_type}</span>
                      <span>Case: {rec.case_id ?? 'Unknown'}</span>
                    </div>
                    {(rec.source_file || rec.source_row != null) && (
                      <div className="text-slate-500 font-mono text-[9px]">
                        Source: {rec.source_file ?? 'N/A'}{rec.source_row != null ? ` : row ${rec.source_row}` : ''}
                      </div>
                    )}
                    {rec.timestamp && (
                      <div className="text-slate-500 font-mono text-[9px]">
                        Observed: {rec.timestamp}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legal / Ethics Notice */}
          <div className="border border-brand-border/60 rounded p-2 text-[9px] text-slate-500 leading-relaxed font-mono">
            Candidate association produced by GraphSAGE link prediction. This record is for investigative guidance only and does not establish guilt or unlawful conduct.
          </div>
        </div>
      </div>
    )
  }

  // ── Render Standard Confirmed Graph Edge ──────────────────────────────────
  const srcId = edge.source.normalized_number ?? edge.source.normalized_identifier ?? '?'
  const tgtId = edge.target.normalized_number ?? edge.target.normalized_identifier ?? '?'

  return (
    <div className="absolute top-4 right-4 z-30 w-80 bg-brand-panel/95 border border-brand-borderLight backdrop-blur-md rounded-xl shadow-2xl text-xs overflow-y-auto max-h-[80vh]">
      <div className="px-3.5 py-3 border-b border-brand-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-brand-cyan/10 text-brand-cyan border border-brand-cyan/20">
            {edge.relationship_type}
          </span>
          <span className="text-slate-300 text-xs">Edge</span>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">×</button>
      </div>

      <div className="p-3.5 space-y-3">
        {/* Source → Target */}
        <div className="flex items-center gap-2 bg-[#070D14] rounded border border-brand-border px-3 py-2">
          <span className="font-mono text-brand-green text-[11px] truncate flex-1">{srcId}</span>
          <svg className="w-4 h-4 text-slate-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path d="M14 5l7 7m0 0l-7 7m7-7H3" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
          </svg>
          <span className="font-mono text-brand-amber text-[11px] truncate flex-1 text-right">{tgtId}</span>
        </div>

        {/* Event data */}
        {edge.event && (
          <div className="space-y-1.5">
            {edge.event.timestamp_utc && (
              <div className="flex justify-between">
                <span className="text-slate-500">Timestamp (UTC)</span>
                <span className="text-slate-300 font-mono text-[11px]">{edge.event.timestamp_utc.slice(0,19).replace('T',' ')}</span>
              </div>
            )}
            {edge.event.duration_seconds != null && (
              <div className="flex justify-between">
                <span className="text-slate-500">Duration</span>
                <span className="text-slate-300">{edge.event.duration_seconds}s</span>
              </div>
            )}
            {edge.event.amount != null && (
              <div className="flex justify-between">
                <span className="text-slate-500">Amount</span>
                <span className="text-slate-300 font-mono">{edge.event.currency} {edge.event.amount.toLocaleString()}</span>
              </div>
            )}
            {edge.event.transaction_type && (
              <div className="flex justify-between">
                <span className="text-slate-500">Txn Type</span>
                <span className="text-slate-300">{edge.event.transaction_type}</span>
              </div>
            )}
          </div>
        )}

        {/* Provenance */}
        {edge.provenance && (
          <div className="bg-[#070D14] rounded border border-brand-border p-2.5 space-y-1.5">
            <div className="text-[10px] text-slate-500 uppercase font-mono">Evidence Provenance</div>
            {edge.provenance.source_file_name && (
              <div className="flex justify-between">
                <span className="text-slate-500 text-[11px]">Source File</span>
                <span className="text-brand-cyan text-[11px] truncate max-w-[160px]">{edge.provenance.source_file_name}</span>
              </div>
            )}
            {edge.provenance.source_row_number != null && (
              <div className="flex justify-between">
                <span className="text-slate-500 text-[11px]">Row #</span>
                <span className="text-slate-300 font-mono text-[11px]">{edge.provenance.source_row_number}</span>
              </div>
            )}
            {edge.provenance.verification_status && (
              <div className="flex justify-between">
                <span className="text-slate-500 text-[11px]">Integrity</span>
                <span className={`text-[11px] font-mono ${edge.provenance.verification_status === 'VERIFIED' ? 'text-brand-green' : 'text-brand-red'}`}>
                  {edge.provenance.verification_status}
                </span>
              </div>
            )}
            {edge.provenance.source_hash && (
              <div className="mt-1">
                <div className="text-[10px] text-slate-500 mb-0.5">SHA-256</div>
                <div className="font-mono text-[10px] text-slate-400 break-all">{edge.provenance.source_hash.slice(0,32)}…</div>
              </div>
            )}
          </div>
        )}

        {/* Limitations */}
        {edge.limitations && edge.limitations.length > 0 && (
          <div className="border border-brand-amber/30 rounded p-2.5 bg-brand-amber/5">
            <div className="text-[10px] text-brand-amber font-semibold uppercase font-mono mb-1">⚠ Evidentiary Limitations</div>
            {edge.limitations.map((l, i) => (
              <p key={i} className="text-[10px] text-slate-400 leading-relaxed">• {l}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
