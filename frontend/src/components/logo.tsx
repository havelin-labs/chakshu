import { cn } from "@/lib/utils"

/**
 * Chakshu mark in Havelin's line-drawn node/link style: an eye outline whose
 * corners are teal nodes, with a teal iris. Lines use currentColor so the mark
 * follows light and dark mode. public/favicon.svg is the same drawing on a
 * light disc for browser tabs.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="4 12 56 40" className={cn("h-7 w-auto", className)} aria-hidden>
      <path
        d="M10 32c6-9.4 13.4-14 22-14s16 4.6 22 14c-6 9.4-13.4 14-22 14s-16-4.6-22-14Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <circle cx="32" cy="32" r="7.5" fill="none" stroke="var(--brand-teal)" strokeWidth="3" />
      <circle cx="32" cy="32" r="2.8" fill="var(--brand-teal)" />
      <circle cx="10" cy="32" r="3.6" fill="var(--brand-teal)" />
      <circle cx="54" cy="32" r="3.6" fill="var(--brand-teal)" />
    </svg>
  )
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="font-heading text-xl font-bold tracking-tight">Chakshu</span>
    </span>
  )
}
