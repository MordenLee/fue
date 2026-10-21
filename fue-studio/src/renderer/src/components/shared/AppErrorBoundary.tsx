import React from 'react'

interface AppErrorBoundaryState {
  hasError: boolean
  message: string
}

export class AppErrorBoundary extends React.Component<React.PropsWithChildren, AppErrorBoundaryState> {
  constructor(props: React.PropsWithChildren) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      hasError: true,
      message: error?.message || 'Unknown render error'
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('Renderer crash captured by AppErrorBoundary:', error, errorInfo)
  }

  render(): React.ReactNode {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="h-screen w-screen flex items-center justify-center bg-neutral-950 text-neutral-100 px-6">
        <div className="max-w-xl w-full rounded-xl border border-white/10 bg-white/5 p-6">
          <h1 className="text-lg font-semibold mb-2">界面发生错误</h1>
          <p className="text-sm text-neutral-300 mb-4">
            程序已拦截本次渲染异常，避免黑白屏。你可以点击下方按钮刷新恢复。
          </p>
          <div className="text-xs text-neutral-400 break-words mb-5">{this.state.message}</div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="px-3 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-sm"
          >
            刷新页面
          </button>
        </div>
      </div>
    )
  }
}
