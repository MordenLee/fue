import { useEffect } from 'react'
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react'

export interface ToastData {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  duration?: number
}

const icons = {
  success: <CheckCircle className="h-4 w-4 text-green-400" />,
  error: <AlertCircle className="h-4 w-4 text-red-400" />,
  warning: <AlertTriangle className="h-4 w-4 text-yellow-400" />,
  info: <Info className="h-4 w-4 text-blue-400" />
}

const bgColors = {
  success: 'border-green-500/30 bg-green-50 dark:bg-green-900/30',
  error: 'border-red-500/30 bg-red-50 dark:bg-red-900/30',
  warning: 'border-yellow-500/30 bg-yellow-50 dark:bg-yellow-900/30',
  info: 'border-blue-500/30 bg-blue-50 dark:bg-blue-900/30'
}

interface ToastItemProps {
  toast: ToastData
  onDismiss: (id: string) => void
}

export function ToastItem({ toast, onDismiss }: ToastItemProps) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), toast.duration ?? 4000)
    return () => clearTimeout(timer)
  }, [toast.id, toast.duration, onDismiss])

  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg
        animate-in slide-in-from-right fade-in-0 ${bgColors[toast.type]}`}
    >
      {icons[toast.type]}
      <span className="text-sm text-neutral-800 dark:text-white flex-1">{toast.message}</span>
      <button onClick={() => onDismiss(toast.id)} className="text-neutral-400 hover:text-neutral-700 dark:hover:text-white">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

export function ToastContainer({ toasts, onDismiss }: { toasts: ToastData[]; onDismiss: (id: string) => void }) {
  return (
    <div className="fixed top-10 right-4 z-[100] flex flex-col gap-2 w-80">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  )
}
