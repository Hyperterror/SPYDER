'use client'

type BorderColor = 'cyan' | 'amber' | 'red' | 'purple'

const BORDER: Record<BorderColor, string> = {
  cyan:   'action-card-cyan',
  amber:  'action-card-amber',
  red:    'action-card-red',
  purple: 'action-card-purple',
}
const BADGE_COLORS: Record<BorderColor, string> = {
  cyan:   'bg-brand-cyan/15   text-brand-cyan   border-brand-cyan/30',
  amber:  'bg-brand-amber/15  text-brand-amber  border-brand-amber/30',
  red:    'bg-brand-red/15    text-brand-red    border-brand-red/30',
  purple: 'bg-brand-purple/15 text-brand-purple border-brand-purple/30',
}
const ICON_BG: Record<BorderColor, string> = {
  cyan:   'bg-brand-cyan/10   text-brand-cyan',
  amber:  'bg-brand-amber/10  text-brand-amber',
  red:    'bg-brand-red/10    text-brand-red',
  purple: 'bg-brand-purple/10 text-brand-purple',
}

interface ActionQueueItemProps {
  title: string
  badge: string
  description: React.ReactNode
  timeAgo: string
  color?: BorderColor
  icon?: React.ReactNode
  onReview?: () => void
}

export default function ActionQueueItem({
  title,
  badge,
  description,
  timeAgo,
  color = 'red',
  icon,
  onReview,
}: ActionQueueItemProps) {
  return (
    <div className={`p-3 bg-brand-surface border border-brand-border rounded-md ${BORDER[color]} flex items-start justify-between gap-3 hover:bg-brand-surface/90 transition-colors`}>
      <div className="flex items-start space-x-3">
        {icon && (
          <div className={`w-7 h-7 rounded-full ${ICON_BG[color]} flex items-center justify-center shrink-0 mt-0.5`}>
            {icon}
          </div>
        )}
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-semibold text-white">{title}</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${BADGE_COLORS[color]}`}>
              {badge}
            </span>
          </div>
          <p className="text-[11px] text-slate-300 mt-1 leading-snug">{description}</p>
        </div>
      </div>
      <div className="text-right shrink-0 flex flex-col items-end space-y-2">
        <span className="text-[10px] font-mono text-slate-400">{timeAgo}</span>
        {onReview && (
          <button
            onClick={onReview}
            className="px-2.5 py-1 text-[11px] font-medium bg-brand-panel hover:bg-brand-cyan/20 text-brand-cyan border border-brand-borderLight hover:border-brand-cyan/40 rounded transition-all active:scale-95"
          >
            Review
          </button>
        )}
      </div>
    </div>
  )
}
