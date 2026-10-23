import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { relativeText } from "@/lib/people"

const full = new Intl.DateTimeFormat("en", { dateStyle: "full", timeStyle: "short" })

// "3 days ago" within a month, "on Mar 4, 2026" after. The full time is in a tooltip, or in the title
// when `plain` (inside a card, where the stretched link must stay the only tab stop).
export function RelativeDate({ iso, plain = false }: { iso: string; plain?: boolean }) {
  const text = relativeText(iso)
  const title = full.format(new Date(iso))
  if (plain) {
    return (
      <time dateTime={iso} title={title}>
        {text}
      </time>
    )
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <time dateTime={iso} tabIndex={0} className="rounded-sm underline decoration-dotted underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        }
      >
        {text}
      </TooltipTrigger>
      <TooltipContent>{title}</TooltipContent>
    </Tooltip>
  )
}
