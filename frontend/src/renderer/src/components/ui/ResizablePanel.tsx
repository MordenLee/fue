import { useRef, useState, useCallback, useEffect } from 'react'

interface ResizablePanelProps {
  children: React.ReactNode
  defaultWidth: number
  minWidth?: number
  maxWidth?: number
  side?: 'left' | 'right'
  className?: string
  storageKey?: string
}

export function ResizablePanel({
  children, defaultWidth, minWidth = 150, maxWidth = 600,
  side = 'left', className = '', storageKey
}: ResizablePanelProps) {
  const [width, setWidth] = useState(() => {
    if (storageKey) {
      const saved = localStorage.getItem(storageKey)
      if (saved) return Number(saved)
    }
    return defaultWidth
  })

  const panelRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    const startX = e.clientX
    const startWidth = width

    const onMouseMove = (ev: MouseEvent) => {
      if (!isDragging.current) return
      const delta = side === 'left' ? ev.clientX - startX : startX - ev.clientX
      const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + delta))
      setWidth(newWidth)
    }

    const onMouseUp = () => {
      isDragging.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [width, minWidth, maxWidth, side])

  useEffect(() => {
    if (storageKey) localStorage.setItem(storageKey, String(width))
  }, [width, storageKey])

  return (
    <div ref={panelRef} className={`relative flex shrink-0 h-full overflow-hidden ${className}`} style={{ width }}>
      {children}
      <div
        onMouseDown={onMouseDown}
        className={`absolute top-0 h-full w-1 cursor-col-resize z-10
          hover:bg-blue-500/50 active:bg-blue-500/70 transition-colors
          ${side === 'left' ? 'right-0' : 'left-0'}`}
      />
    </div>
  )
}
