import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

// Havelin's eyebrow badge: small uppercase label with a faint teal outline.
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block rounded-[4px] border border-brand-teal/30 px-3 py-1 text-xs font-semibold tracking-wider text-brand-teal-ink uppercase",
        className,
      )}
    >
      {children}
    </span>
  )
}
