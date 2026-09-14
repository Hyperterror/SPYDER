'use client'

type Variant =
  | 'in-progress' | 'high-priority' | 'under-review' | 'active'
  | 'verified' | 'mismatch' | 'unverified' | 'verification-failed'
  | 'pending' | 'processing' | 'completed' | 'partially-completed' | 'failed'
  | 'draft' | 'on-hold' | 'closed'

const MAP: Record<Variant, { label: string; classes: string; dot?: string }> = {
  'in-progress':          { label: 'In Progress',          classes: 'text-brand-green  bg-brand-green/10  border-brand-green/20',  dot: 'bg-brand-green  animate-pulse' },
  'high-priority':        { label: 'High Priority',         classes: 'text-brand-red    bg-brand-red/10    border-brand-red/20',    dot: 'bg-brand-red' },
  'under-review':         { label: 'Under Review',          classes: 'text-brand-amber  bg-brand-amber/10  border-brand-amber/20',  dot: 'bg-brand-amber' },
  'active':               { label: 'Active',                classes: 'text-brand-green  bg-brand-green/10  border-brand-green/20',  dot: 'bg-brand-green  animate-pulse' },
  'verified':             { label: 'Verified',              classes: 'text-brand-green  bg-brand-green/10  border-brand-green/20' },
  'mismatch':             { label: 'Mismatch',              classes: 'text-brand-red    bg-brand-red/10    border-brand-red/20' },
  'unverified':           { label: 'Unverified',            classes: 'text-slate-400    bg-slate-800/40    border-slate-700/40' },
  'verification-failed':  { label: 'Verify Failed',         classes: 'text-brand-red    bg-brand-red/10    border-brand-red/20' },
  'pending':              { label: 'Pending',               classes: 'text-slate-400    bg-slate-800/40    border-slate-700/40' },
  'processing':           { label: 'Processing',            classes: 'text-brand-cyan   bg-brand-cyan/10   border-brand-cyan/20' },
  'completed':            { label: 'Completed',             classes: 'text-brand-green  bg-brand-green/10  border-brand-green/20' },
  'partially-completed':  { label: 'Partial',               classes: 'text-brand-amber  bg-brand-amber/10  border-brand-amber/20' },
  'failed':               { label: 'Failed',                classes: 'text-brand-red    bg-brand-red/10    border-brand-red/20' },
  'draft':                { label: 'Draft',                 classes: 'text-slate-400    bg-slate-800/40    border-slate-700/40' },
  'on-hold':              { label: 'On Hold',               classes: 'text-brand-amber  bg-brand-amber/10  border-brand-amber/20' },
  'closed':               { label: 'Closed',               classes: 'text-slate-400    bg-slate-800/40    border-slate-700/40' },
}

function toVariant(raw: string): Variant {
  return (raw.toLowerCase().replace(/_/g, '-').replace(' ', '-')) as Variant
}

export default function StatusBadge({
  status,
  label,
}: {
  status: string
  label?: string
}) {
  const v = toVariant(status)
  const cfg = MAP[v] ?? { label: status, classes: 'text-slate-400 bg-slate-800/40 border-slate-700/40' }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${cfg.classes}`}>
      {cfg.dot && (
        <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${cfg.dot}`} />
      )}
      {label ?? cfg.label}
    </span>
  )
}
