import { cn } from "@/lib/utils"

// The icon is public/favicon.svg, so the browser tab and the header always match.
export function Logo({ className, showWordmark = true }: { className?: string; showWordmark?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <img src="/favicon.svg" alt="" className="size-8 rounded-[10px] shadow-sm" />
      {showWordmark && (
        <span className="text-brand-gradient text-xl font-bold leading-none tracking-tight">chakshu</span>
      )}
    </span>
  )
}
