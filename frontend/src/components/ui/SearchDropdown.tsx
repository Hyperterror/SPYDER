'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { casesApi, intelligenceApi } from '@/lib/api'
import type { Case } from '@/types'

interface SearchSuggestion {
  type: 'CASE' | 'LEAD' | 'ENTITY'
  label: string
  sub?: string
  caseRef?: string
  href: string
}

const TYPE_COLORS: Record<string, string> = {
  ENTITY: 'bg-brand-cyan/10 text-brand-cyan',
  LEAD: 'bg-brand-purple/10 text-brand-purple',
  CASE: 'bg-brand-amber/10 text-brand-amber',
}

export default function SearchDropdown() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<SearchSuggestion[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [casesRes, leadsRes] = await Promise.all([
          casesApi.list().catch(() => ({ data: [] as Case[] })),
          intelligenceApi.getLeads({ limit: 8 }).catch(() => ({ data: { leads: [] } })),
        ])
        const next: SearchSuggestion[] = []
        for (const c of (casesRes.data || []).slice(0, 6)) {
          next.push({
            type: 'CASE',
            label: c.case_code,
            sub: c.title,
            caseRef: c.status,
            href: `/cases/${c.id}/graph`,
          })
        }
        for (const l of (leadsRes.data?.leads || []).slice(0, 6)) {
          next.push({
            type: 'LEAD',
            label: `${l.source_entity} ↔ ${l.target_entity}`,
            sub: `Score ${l.confidence.toFixed(2)}`,
            caseRef: l.priority,
            href: `/leads/${encodeURIComponent(l.lead_id)}`,
          })
        }
        setItems(next)
      } catch {
        setItems([])
      }
    }
    load()
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!dropRef.current?.contains(e.target as Node) && !inputRef.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const qLower = query.trim().toLowerCase()
  const filtered = qLower
    ? items.filter(
        (s) => s.label.toLowerCase().includes(qLower) || (s.sub ?? '').toLowerCase().includes(qLower)
      )
    : items

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && query.trim()) {
      setOpen(false)
      router.push(`/entities/${encodeURIComponent(query.trim())}`)
    }
  }

  return (
    <div className="relative flex-1 max-w-xl mx-6">
      <div className="relative flex items-center">
        <svg className="absolute left-3.5 w-4 h-4 text-slate-400 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search cases, leads, or enter entity ID (e.g. PER_ALPHA_01)..."
          className="w-full h-9 pl-10 pr-16 bg-[#0B131E] border border-brand-border text-sm rounded-md text-slate-100 placeholder-slate-400 focus:outline-none focus:border-brand-cyan focus:ring-1 focus:ring-brand-cyan transition-all"
        />
        <div className="absolute right-2.5 flex items-center pointer-events-none">
          <span className="text-[11px] font-mono text-slate-400 bg-[#162338] px-1.5 py-0.5 rounded border border-brand-border/60">
            Ctrl K
          </span>
        </div>
      </div>

      {open && (
        <div ref={dropRef} className="absolute left-0 right-0 top-11 bg-brand-panel border border-brand-borderLight rounded-lg shadow-2xl overflow-hidden z-50 py-2">
          <div className="px-3 py-1 text-[11px] font-mono tracking-wider text-slate-400 uppercase flex justify-between">
            <span>Authorized Matches</span>
            {query.trim() && (
              <span className="text-brand-cyan">Press Enter for Entity Profile →</span>
            )}
          </div>
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-xs text-slate-400">
              {query.trim()
                ? `Press Enter to inspect entity "${query.trim()}"`
                : 'No active matches loaded yet.'}
            </div>
          ) : (
            filtered.map((s, i) => (
              <div
                key={i}
                onClick={() => { setOpen(false); router.push(s.href) }}
                className="hover:bg-brand-surface px-3 py-2 cursor-pointer flex items-center justify-between text-xs text-slate-200 border-b border-brand-border/40 last:border-0"
              >
                <div className="flex items-center space-x-2 truncate">
                  <span className={`px-1.5 py-0.5 text-[10px] rounded shrink-0 ${TYPE_COLORS[s.type] ?? 'bg-slate-800 text-slate-300'}`}>
                    {s.type}
                  </span>
                  <span className="font-mono text-white truncate">{s.label}</span>
                  {s.sub && <span className="text-slate-400 truncate">{s.sub}</span>}
                </div>
                {s.caseRef && <span className="text-[11px] text-slate-400 flex-shrink-0 ml-2">{s.caseRef}</span>}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
