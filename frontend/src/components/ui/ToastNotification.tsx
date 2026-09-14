'use client'

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ToastMessage } from '@/types'

// ─── Context ─────────────────────────────────────────────────────────────
interface ToastCtx { toast: (msg: string, type?: ToastMessage['type']) => void }
const ToastContext = createContext<ToastCtx>({ toast: () => {} })
export const useToast = () => useContext(ToastContext)

// ─── Individual Toast ─────────────────────────────────────────────────────
function Toast({ message, type, onRemove }: ToastMessage & { onRemove: () => void }) {
  const [leaving, setLeaving] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    timerRef.current = setTimeout(() => {
      setLeaving(true)
      setTimeout(onRemove, 200)
    }, 3500)
    return () => clearTimeout(timerRef.current)
  }, [onRemove])

  const dotColor =
    type === 'error' ? 'bg-brand-red' :
    type === 'warn'  ? 'bg-brand-amber' :
                       'bg-brand-cyan'

  return (
    <div
      className={`bg-brand-surface border border-brand-borderLight text-slate-100 px-4 py-2.5 rounded-lg shadow-2xl text-xs flex items-center space-x-2 pointer-events-auto ${leaving ? 'toast-out' : 'toast-in'}`}
    >
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-pulse flex-shrink-0`} />
      <span>{message}</span>
      <button
        onClick={() => { setLeaving(true); setTimeout(onRemove, 200) }}
        className="ml-2 text-slate-400 hover:text-white text-sm leading-none"
      >
        ×
      </button>
    </div>
  )
}

// ─── Provider ─────────────────────────────────────────────────────────────
export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const toast = useCallback((message: string, type: ToastMessage['type'] = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { id, message, type }])
  }, [])

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col space-y-2 pointer-events-none">
        {toasts.map((t) => (
          <Toast key={t.id} {...t} onRemove={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
