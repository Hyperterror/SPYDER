'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import SearchDropdown from '@/components/ui/SearchDropdown'
import { logout, getStoredUser } from '@/lib/auth'
import type { User } from '@/types'

export default function TopHeader() {
  const router = useRouter()
  const [user, setUser]           = useState<User | null>(null)
  const [bellOpen, setBellOpen]   = useState(false)
  const [profileOpen, setProfile] = useState(false)
  const bellRef    = useRef<HTMLDivElement>(null)
  const profileRef = useRef<HTMLDivElement>(null)

  useEffect(() => { setUser(getStoredUser()) }, [])

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!bellRef.current?.contains(e.target as Node))    setBellOpen(false)
      if (!profileRef.current?.contains(e.target as Node)) setProfile(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleLogout = async () => {
    await logout()
    router.push('/login')
  }

  const initials = user?.display_name
    ? user.display_name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
    : 'SG'

  return (
    <header className="h-14 border-b border-brand-border bg-brand-bg/95 backdrop-blur-md px-4 flex items-center justify-between z-30 shrink-0 select-none">
      {/* Logo */}
      <div className="flex items-center space-x-3 w-60 shrink-0">
        <Link href="/" className="flex items-center focus:outline-none">
          <span className="text-brand-cyan font-mono font-bold text-lg tracking-widest">
            SPYDER<span className="text-white">-DETECT</span>
          </span>
        </Link>
      </div>

      {/* Search */}
      <SearchDropdown />

      {/* Actions */}
      <div className="flex items-center space-x-4 shrink-0">
        {/* Import CTA */}
        <Link
          href="/import"
          className="h-9 px-4 bg-brand-cyan/15 hover:bg-brand-cyan/25 border border-brand-cyan/50 text-brand-cyan rounded-md text-xs font-semibold flex items-center space-x-2 transition-all shadow-[0_0_12px_rgba(0,229,255,0.15)] active:scale-95"
        >
          <span className="text-base font-bold leading-none">+</span>
          <span>Import Evidence</span>
        </Link>

        {/* Bell */}
        <div className="relative" ref={bellRef}>
          <button
            onClick={() => setBellOpen((v) => !v)}
            className="w-9 h-9 flex items-center justify-center rounded-md border border-brand-border hover:border-brand-borderLight text-slate-300 hover:text-white transition-colors relative"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
            </svg>
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-brand-red rounded-full ring-2 ring-brand-bg" />
          </button>

          {bellOpen && (
            <div className="absolute right-0 mt-2 w-80 bg-brand-panel border border-brand-borderLight rounded-lg shadow-2xl p-3 z-50">
              <div className="flex items-center justify-between pb-2 border-b border-brand-border">
                <span className="text-xs font-semibold text-white">System Alerts</span>
                <span className="text-[10px] text-brand-cyan hover:underline cursor-pointer">Mark all read</span>
              </div>
              <div className="mt-2 space-y-2 text-xs">
                <div className="p-2 rounded bg-brand-surface/70 border border-brand-border">
                  <div className="text-brand-amber font-medium">Contradiction Flagged</div>
                  <div className="text-slate-400 text-[11px] mt-0.5">Cell tower ping mismatch detected.</div>
                </div>
                <div className="p-2 rounded bg-brand-surface/70 border border-brand-border">
                  <div className="text-brand-cyan font-medium">Hash Integrity Verified</div>
                  <div className="text-slate-400 text-[11px] mt-0.5">Bank_Statements.xlsx signed &amp; stamped.</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Profile */}
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => setProfile((v) => !v)}
            className="flex items-center space-x-2.5 pl-1.5 pr-2 py-1 rounded-md hover:bg-brand-surface transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-slate-700/80 border border-slate-500/40 text-brand-cyan text-xs font-bold flex items-center justify-center">
              {initials}
            </div>
            <div className="text-left leading-tight hidden sm:block">
              <div className="text-xs font-medium text-slate-100 flex items-center gap-1">
                {user?.display_name ?? 'Investigator'}
                <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M19 9l-7 7-7-7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                </svg>
              </div>
              <div className="text-[11px] text-slate-400">{user?.role ?? 'INVESTIGATOR'}</div>
            </div>
          </button>

          {profileOpen && (
            <div className="absolute right-0 mt-2 w-48 bg-brand-panel border border-brand-borderLight rounded-lg shadow-xl py-1 z-50 text-xs">
              <div className="px-3 py-2 border-b border-brand-border text-slate-400">
                Role: <span className="font-mono text-slate-200">{user?.role}</span>
              </div>
              <a href="#" className="block px-3 py-2 hover:bg-brand-surface text-slate-200">Security Clearance</a>
              <a href="#" className="block px-3 py-2 hover:bg-brand-surface text-slate-200">Audit Logs</a>
              <div className="border-t border-brand-border" />
              <button
                onClick={handleLogout}
                className="w-full text-left block px-3 py-2 hover:bg-brand-surface text-brand-red"
              >
                Disconnect Session
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
