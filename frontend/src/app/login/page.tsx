'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { login, isAuthenticated } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail]       = useState('investigator@spyder.gov')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  useEffect(() => {
    if (isAuthenticated()) router.replace('/')
  }, [router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      router.replace('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-bg flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background grid */}
      <div className="absolute inset-0 canvas-bg-grid opacity-30 pointer-events-none" />

      {/* Glow orb */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-brand-cyan/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-brand-cyan font-mono font-bold text-2xl tracking-widest">
            SPYDER<span className="text-white">-DETECT</span>
          </h1>
          <p className="text-slate-400 text-xs mt-2 font-mono tracking-wider uppercase">
            Secure Criminal Intelligence Platform
          </p>
        </div>

        {/* Card */}
        <div className="bg-brand-panel border border-brand-border rounded-xl p-6 shadow-2xl">
          <div className="mb-5">
            <h2 className="text-white font-semibold text-sm">Authenticate</h2>
            <p className="text-slate-400 text-[11px] mt-0.5">Enter your investigator credentials</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] font-medium text-slate-400 mb-1">
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-[#0B131E] border border-brand-border rounded-md px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-cyan focus:ring-1 focus:ring-brand-cyan transition-all"
                placeholder="investigator@spyder.gov"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-slate-400 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full bg-[#0B131E] border border-brand-border rounded-md px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-cyan focus:ring-1 focus:ring-brand-cyan transition-all"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-brand-red text-[11px] bg-brand-red/10 border border-brand-red/20 rounded px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-brand-cyan hover:bg-brand-cyan/80 disabled:opacity-50 text-black font-semibold text-xs rounded-md transition-all active:scale-95 glow-cyan-btn"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Authenticating…
                </span>
              ) : (
                'Authenticate'
              )}
            </button>
          </form>

          <div className="mt-4 text-center text-[10px] text-slate-500 font-mono">
            Demo: investigator@spyder.gov / Invest@1234
          </div>
        </div>

        <p className="text-center text-[10px] text-slate-600 font-mono mt-4 tracking-widest uppercase">
          SECURE · ANALYSE · EMPOWER
        </p>
      </div>
    </div>
  )
}
