'use client'

import Link from 'next/link'
import type { GraphNode } from '@/types'

const ENTITY_COLORS: Record<string, string> = {
  Phone:    'text-brand-green   bg-brand-green/10   border-brand-green/20',
  Account:  'text-brand-amber   bg-brand-amber/10   border-brand-amber/20',
  Device:   'text-brand-cyan    bg-brand-cyan/10    border-brand-cyan/20',
  Tower:    'text-slate-300     bg-slate-800/40     border-slate-700/40',
  Document: 'text-brand-purple  bg-brand-purple/10  border-brand-purple/20',
}

interface NodeInspectorProps {
  node: GraphNode | null
  onClose: () => void
}

export default function NodeInspector({ node, onClose }: NodeInspectorProps) {
  if (!node) return null

  const label  = Array.isArray(node.labels) ? node.labels[0] ?? 'Node' : 'Node'
  const colorClass = ENTITY_COLORS[label] ?? 'text-slate-300 bg-slate-800/40 border-slate-700/40'
  const identifier = node.normalized_number ?? node.normalized_identifier ?? node.id ?? '—'

  return (
    <div className="absolute top-4 right-4 z-30 w-72 bg-brand-panel/95 border border-brand-borderLight backdrop-blur-md rounded-xl shadow-2xl text-xs">
      <div className="px-3.5 py-3 border-b border-brand-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${colorClass}`}>
            {label.toUpperCase()}
          </span>
          <span className="font-semibold text-white text-xs">{label}</span>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">×</button>
      </div>

      <div className="p-3.5 space-y-3">
        {/* Identifier */}
        <div className="bg-[#070D14] rounded border border-brand-border px-3 py-2">
          <div className="text-[10px] text-slate-500 uppercase font-mono mb-0.5">Identifier</div>
          <div className="font-mono text-white text-xs break-all">{identifier}</div>
        </div>

        {/* Properties */}
        <div className="space-y-1.5">
          {Boolean(node.first_seen_at) && (
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">First Seen</span>
              <span className="text-slate-300 font-mono text-[11px]">{String(node.first_seen_at).slice(0,10)}</span>
            </div>
          )}
          {Boolean(node.last_seen_at) && (
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">Last Seen</span>
              <span className="text-slate-300 font-mono text-[11px]">{String(node.last_seen_at).slice(0,10)}</span>
            </div>
          )}
          {Boolean(node.imei) && (
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">IMEI</span>
              <span className="text-slate-300 font-mono text-[11px]">{String(node.imei)}</span>
            </div>
          )}
          {Boolean(node.tower_id) && (
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">Tower ID</span>
              <span className="text-slate-300 font-mono text-[11px]">{String(node.tower_id)}</span>
            </div>
          )}
          {Boolean(node.account_type) && (
            <div className="flex justify-between">
              <span className="text-slate-500 text-[11px]">Account Type</span>
              <span className="text-slate-300 text-[11px]">{String(node.account_type)}</span>
            </div>
          )}
        </div>

        {/* SHA if Document */}
        {label === 'Document' && Boolean(node.sha256_hash) && (
          <div className="bg-[#070D14] rounded border border-brand-border px-3 py-2">
            <div className="text-[10px] text-slate-500 uppercase font-mono mb-0.5">SHA-256</div>
            <div className="font-mono text-brand-cyan text-[10px] break-all">{String(node.sha256_hash)}</div>
          </div>
        )}

        <div className="pt-1">
          <Link
            href={`/entities/${encodeURIComponent(String(identifier))}`}
            className="block w-full text-center py-1.5 rounded bg-brand-cyan/15 hover:bg-brand-cyan/25 border border-brand-cyan/40 text-brand-cyan text-[11px] font-semibold transition"
          >
            Open Entity Profile →
          </Link>
        </div>

        <p className="text-[10px] text-slate-500 italic leading-relaxed border-t border-brand-border/40 pt-2">
          Node data is derived from evidence records. It does not establish identity or criminal conduct.
        </p>
      </div>
    </div>
  )
}
