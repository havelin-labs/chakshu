import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

const tones = {
  info: "border-brand-teal/30 bg-brand-teal-tint",
  error: "border-destructive/40 bg-destructive/10 text-destructive",
} as const

export function Notice({ tone = "info", children }: { tone?: keyof typeof tones; children: ReactNode }) {
  return <div className={cn("rounded-[4px] border px-4 py-3 text-sm", tones[tone])}>{children}</div>
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null
  return <Notice tone="error">{error instanceof Error ? error.message : String(error)}</Notice>
}
