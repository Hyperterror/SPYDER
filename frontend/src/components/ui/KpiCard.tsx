'use client'

import { ReactNode } from 'react'

type ColorVariant = 'cyan' | 'red' | 'amber' | 'purple' | 'green'

const COLORS: Record<ColorVariant, { glow: string; hover: string; icon: string; trend: string }> = {
  cyan:   { glow: 'glow-cyan-card',   hover: 'hover:border-brand-cyan/60',   icon: 'text-brand-cyan',   trend: 'text-brand-green' },
  red:    { glow: 'glow-red-card',    hover: 'hover:border-brand-red/60',    icon: 'text-brand-red',    trend: 'text-brand-red' },
  amber:  { glow: 'glow-amber-card',  hover: 'hover:border-brand-amber/60',  icon: 'text-brand-amber',  trend: 'text-brand-amber' },
  purple: { glow: 'glow-purple-card', hover: 'hover:border-brand-purple/60', icon: 'text-brand-purple', trend: 'text-brand-green' },
  green:  { glow: 'glow-cyan-card',   hover: 'hover:border-brand-green/60',  icon: 'text-brand-green',  trend: 'text-brand-green' },
}

interface KpiCardProps {
  icon: ReactNode
  label: string
  value: number | string
  trendDelta?: number
  trendLabel?: string
  color?: ColorVariant
  onClick?: () => void
}

export default function KpiCard({
  icon,
  label,
  value,
  trendDelta,
  trendLabel = 'vs. last week',
  color = 'cyan',
  onClick,
}: KpiCardProps) {
  const c = COLORS[color]
  return (
    <div
      onClick={onClick}
      className={`bg-brand-panel border border-brand-border rounded-lg p-4 cursor-pointer ${c.hover} transition-all group ${c.glow} relative overflow-hidden`}
    >
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-md bg-brand-surface border border-brand-border flex items-center justify-center ${c.icon} group-hover:border-opacity-40 transition-colors`}>
          {icon}
        </div>
        <div className="text-right">
          <span className="text-xs text-slate-400 block font-medium">{label}</span>
          <div className="text-3xl font-extrabold text-white mt-1 leading-none">{value}</div>
        </div>
      </div>
      {trendDelta !== undefined && (
        <div className={`mt-3 flex items-center text-[11px] ${c.trend} space-x-1`}>
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path d="M5 10l7-7m0 0l7 7m-7-7v18" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />
          </svg>
          <span className="font-semibold">{trendDelta}</span>
          <span className="text-slate-400 font-normal">{trendLabel}</span>
        </div>
      )}
    </div>
  )
}
