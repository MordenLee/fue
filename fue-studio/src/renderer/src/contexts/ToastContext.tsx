import { createContext, useContext, useCallback, useMemo, useState } from 'react'
import { ToastContainer, type ToastData } from '../components/ui/Toast'

interface ToastContextType {
  toast: (data: Omit<ToastData, 'id'>) => void
  success: (message: string) => void
  error: (message: string) => void
  warning: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextType | null>(null)

let toastId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback((data: Omit<ToastData, 'id'>) => {
    const id = String(++toastId)
    setToasts((prev) => [...prev, { ...data, id }])
  }, [])

  const success = useCallback((message: string) => {
    addToast({ type: 'success', message })
  }, [addToast])

  const error = useCallback((message: string) => {
    addToast({ type: 'error', message })
  }, [addToast])

  const warning = useCallback((message: string) => {
    addToast({ type: 'warning', message })
  }, [addToast])

  const info = useCallback((message: string) => {
    addToast({ type: 'info', message })
  }, [addToast])

  const ctx: ToastContextType = useMemo(() => ({
    toast: addToast,
    success,
    error,
    warning,
    info
  }), [addToast, success, error, warning, info])

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextType {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
