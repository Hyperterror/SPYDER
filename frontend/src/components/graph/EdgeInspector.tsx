'use client'

interface EdgeData {
  edge_id: string
  relationship_type: string
  source: { labels: string[]; normalized_number?: string; normalized_identifier?: string }
  target: { labels: string[]; normalized_number?: string; normalized_identifier?: string }
  event: {
    timestamp_utc?: string
    duration_seconds?: number
    amount?: number
    currency?: string
    transaction_id?: string
    transaction_type?: string
  }
  provenance: {
    evidence_id?: string
    source_file_name?: string
    source_row_number?: number
    source_hash?: string
    verification_status?: string
    relationship_status?: string
    confidence_label?: string
  }
  limitations?: string[]
}

interface EdgeInspectorProps {
  edge: EdgeData | null
  onClose: () => void
}

export default function EdgeInspector({ edge, onClose }: EdgeInspectorProps) {
  if (!edge) return null

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

        {/* Provenance */}
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
