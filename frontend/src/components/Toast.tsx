import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { useI18n } from '../i18n/useTranslation'

interface ToastAction {
  label: string
  onClick: () => void
}

interface ToastItem {
  id: number
  message: string
  action?: ToastAction
  variant: 'default' | 'error'
}

interface ConfirmState {
  message: string
  confirmLabel?: string
  danger?: boolean
  resolve: (value: boolean) => void
}

interface UIContextValue {
  toast: (message: string, opts?: { action?: ToastAction; variant?: 'default' | 'error'; duration?: number }) => void
  confirm: (message: string, opts?: { confirmLabel?: string; danger?: boolean }) => Promise<boolean>
}

const UIContext = createContext<UIContextValue | null>(null)

/** Toasts (with optional Undo action) and an in-app confirm dialog to replace
 *  native alert()/confirm(). */
export function useToast(): UIContextValue {
  const ctx = useContext(UIContext)
  if (!ctx) throw new Error('useToast must be used within a UIProvider')
  return ctx
}

let _nextId = 0

export function UIProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null)
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  const dismiss = useCallback((id: number) => {
    setToasts(ts => ts.filter(t => t.id !== id))
    const timer = timers.current[id]
    if (timer) {
      clearTimeout(timer)
      delete timers.current[id]
    }
  }, [])

  const toast = useCallback<UIContextValue['toast']>((message, opts = {}) => {
    const id = ++_nextId
    const item: ToastItem = { id, message, action: opts.action, variant: opts.variant ?? 'default' }
    setToasts(ts => [...ts.slice(-2), item]) // keep at most 3 on screen
    timers.current[id] = setTimeout(() => dismiss(id), opts.duration ?? 5000)
  }, [dismiss])

  const confirm = useCallback<UIContextValue['confirm']>((message, opts = {}) => {
    return new Promise<boolean>(resolve => {
      setConfirmState({ message, confirmLabel: opts.confirmLabel, danger: opts.danger, resolve })
    })
  }, [])

  const closeConfirm = (value: boolean) => {
    setConfirmState(state => {
      state?.resolve(value)
      return null
    })
  }

  return (
    <UIContext.Provider value={{ toast, confirm }}>
      {children}

      {/* Toasts */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[2000] flex flex-col items-center gap-2 pointer-events-none">
        {toasts.map(item => (
          <div
            key={item.id}
            className={`pointer-events-auto flex items-center gap-3 rounded-lg px-4 py-2.5 shadow-xl text-sm border ${
              item.variant === 'error'
                ? 'bg-red-950 border-red-800 text-red-200'
                : 'bg-gray-800 border-gray-700 text-gray-100'
            }`}
          >
            <span>{item.message}</span>
            {item.action && (
              <button
                onClick={() => { item.action!.onClick(); dismiss(item.id) }}
                className="text-blue-400 hover:text-blue-300 font-medium whitespace-nowrap"
              >
                {item.action.label}
              </button>
            )}
            <button onClick={() => dismiss(item.id)} className="text-gray-500 hover:text-gray-300">✕</button>
          </div>
        ))}
      </div>

      {/* Confirm dialog */}
      {confirmState && (
        <div
          className="fixed inset-0 z-[2100] bg-black/60 flex items-center justify-center p-4"
          onClick={() => closeConfirm(false)}
        >
          <div
            className="bg-gray-900 border border-gray-700 rounded-xl max-w-sm w-full p-5 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <p className="text-sm text-gray-200">{confirmState.message}</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => closeConfirm(false)}
                className="px-3 py-1.5 rounded text-sm bg-gray-800 hover:bg-gray-700 text-gray-300"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={() => closeConfirm(true)}
                className={`px-3 py-1.5 rounded text-sm text-white ${
                  confirmState.danger ? 'bg-red-700 hover:bg-red-600' : 'bg-blue-600 hover:bg-blue-700'
                }`}
              >
                {confirmState.confirmLabel ?? t('common.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </UIContext.Provider>
  )
}
