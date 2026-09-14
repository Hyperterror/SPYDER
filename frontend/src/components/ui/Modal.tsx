'use client'

import { useEffect } from 'react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  subtitle?: string
  children: React.ReactNode
  footer?: React.ReactNode
  maxWidth?: string
}

export default function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  maxWidth = 'max-w-xl',
}: ModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    if (open) document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 modal-backdrop flex items-center justify-center p-4">
      <div
        className={`bg-brand-panel border border-brand-borderLight w-full ${maxWidth} rounded-xl shadow-2xl overflow-hidden`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {title && (
          <div className="px-5 py-4 border-b border-brand-border flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white">{title}</h3>
              {subtitle && <p className="text-[11px] text-slate-400 mt-0.5">{subtitle}</p>}
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white text-lg font-bold p-1"
            >
              ×
            </button>
          </div>
        )}

        {/* Body */}
        <div className="p-5">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="px-5 py-3 border-t border-brand-border bg-brand-surface/40">
            {footer}
          </div>
        )}
      </div>
      {/* Backdrop click to close */}
      <div className="absolute inset-0 -z-10" onClick={onClose} />
    </div>
  )
}
