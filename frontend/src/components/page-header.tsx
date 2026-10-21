import type { ReactNode } from "react"

import { Eyebrow } from "@/components/eyebrow"

export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow: string
  title: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl space-y-4">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="text-4xl font-bold tracking-tight">{title}</h1>
        {children && <div className="text-muted-foreground">{children}</div>}
      </div>
      {actions}
    </div>
  )
}
