import type { ReactNode } from "react"

// A title, one sentence on why, and at most one thing to do about it.
export function EmptyState({ title, reason, action }: { title: string; reason?: ReactNode; action?: ReactNode }) {
  return (
    <div className="space-y-2 rounded-[4px] border border-dashed bg-card px-6 py-10 text-center">
      <p className="font-heading text-lg font-semibold">{title}</p>
      {reason && <p className="mx-auto max-w-xl text-sm text-muted-foreground">{reason}</p>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  )
}
