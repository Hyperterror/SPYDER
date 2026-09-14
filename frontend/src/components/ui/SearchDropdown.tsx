'use client'

import { useEffect, useRef, useState } from 'react'

interface SearchSuggestion {
  type: 'PHONE' | 'CASE' | 'ACCOUNT' | 'VEHICLE' | 'DEVICE'
  label: string
  sub?: string
  caseRef?: string
}

const MOCK_SUGGESTIONS: SearchSuggestion[] = [
  { type: 'PHONE',   label: '+91 98XXXXXX12', sub: 'Associated with Suspect X', caseRef: 'Case #25998' },
  { type: 'VEHICLE', label: 'DL01AB1234',     sub: 'Black SUV (Toyota Fortuner)', caseRef: 'Case #25432' },
  { type: 'CASE',    label: 'Operation Falcon', sub: 'Cyber Fraud Ring', caseRef: '#26189' },
  { type: 'ACCOUNT', label: 'rahulsharma@ybl', sub: 'UPI Account', caseRef: 'Case #26189' },
]

const TYPE_COLORS: Record<string, string> = {
  PHONE:   'bg-brand-cyan/10   text-brand-cyan',
  VEHICLE: 'bg-brand-purple/10 text-brand-purple',
  CASE:    'bg-brand-amber/10  text-brand-amber',
  ACCOUNT: 'bg-brand-green/10  text-brand-green',
  DEVICE:  'bg-slate-800/60    text-slate-300',
}

export default function SearchDropdown() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const dropRef  = useRef<HTMLDivElement>(null)

  // Ctrl+K
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

  // Click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!dropRef.current?.contains(e.target as Node) && !inputRef.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = query.length >= 1
    ? MOCK_SUGGESTIONS.filter(
        (s) => s.label.toLowerCase().includes(query.toLowerCase()) ||
               s.sub?.toLowerCase().includes(query.toLowerCase())
      )
    : MOCK_SUGGESTIONS

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
          placeholder="Search people, numbers, accounts, devices, cases..."
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
          <div className="px-3 py-1 text-[11px] font-mono tracking-wider text-slate-400 uppercase">
            Recent Entities &amp; Matches
          </div>
          {filtered.map((s, i) => (
            <div
              key={i}
              onClick={() => setOpen(false)}
              className="hover:bg-brand-surface px-3 py-2 cursor-pointer flex items-center justify-between text-xs text-slate-200 border-b border-brand-border/40 last:border-0"
            >
              <div className="flex items-center space-x-2">
                <span className={`px-1.5 py-0.5 text-[10px] rounded ${TYPE_COLORS[s.type] ?? 'bg-slate-800 text-slate-300'}`}>
                  {s.type}
                </span>
                <span className="font-mono text-white">{s.label}</span>
                {s.sub && <span className="text-slate-400">{s.sub}</span>}
              </div>
              {s.caseRef && <span className="text-[11px] text-slate-400 flex-shrink-0">{s.caseRef}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
