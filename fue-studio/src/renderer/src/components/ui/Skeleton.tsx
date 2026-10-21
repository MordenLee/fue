interface SkeletonProps {
  className?: string
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return <div className={`animate-pulse rounded bg-white/10 ${className}`} />
}

export function SkeletonLine({ width = 'w-full' }: { width?: string }) {
  return <Skeleton className={`h-4 ${width}`} />
}

export function SkeletonCard() {
  return (
    <div className="rounded-lg border border-white/5 bg-white/5 p-4 space-y-3">
      <SkeletonLine width="w-2/3" />
      <SkeletonLine />
      <SkeletonLine width="w-1/2" />
    </div>
  )
}
