import type { PersonTotals } from "@/lib/api"
import { cost, count } from "@/lib/format"
import { deltaText, periodText } from "@/lib/people"

const TILES: { key: keyof PersonTotals; label: string; money?: boolean }[] = [
  { key: "requested", label: "Reviews requested" },
  { key: "prs_reviewed", label: "Their PRs reviewed" },
  { key: "auto_reviews", label: "Automatic reviews of their PRs" },
  { key: "replies", label: "Replies to Chakshu" },
  { key: "cost_triggered", label: "Cost of their requests", money: true },
  { key: "cost_on_own_prs", label: "Cost of reviews on their PRs", money: true },
]

// Six numbers in a fixed order, each against the previous period in neutral words.
export function KpiTiles({ totals, previous, days }: { totals: PersonTotals; previous: PersonTotals; days: number }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {TILES.map(({ key, label, money }) => {
        const format = (n: number) => (money ? cost(n) : count(n))
        return (
          <div key={key} className="space-y-1 rounded-[4px] border bg-card p-4">
            <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</dt>
            <dd className="font-heading text-2xl font-semibold tabular-nums">{format(totals[key])}</dd>
            <dd className="text-xs text-muted-foreground">
              In {periodText(days)}, {deltaText(totals[key], previous[key], days, format)}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}
