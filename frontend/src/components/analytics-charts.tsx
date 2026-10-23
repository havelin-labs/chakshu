import { useState } from "react"

import { cn } from "@/lib/utils"

// Charts for the analytics pages. One series each, in the validated --chart-1 teal,
// so there is no legend to read. Every chart has a table view, and changes are
// shown in neutral ink: more reviews or more spend isn't good or bad by itself.

export function StatTile({
  label,
  value,
  change,
  hint,
}: {
  label: string
  value: string
  change?: number | null
  hint?: string
}) {
  return (
    <div className="space-y-1 rounded-[4px] border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-heading text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">
        {change == null ? (hint ?? "No earlier period to compare") : `${change > 0 ? "▲" : change < 0 ? "▼" : "●"} ${Math.abs(Math.round(change * 100))}% vs previous period`}
      </p>
    </div>
  )
}

type Point = { label: string; value: number }

const HEIGHT = 140
const GAP = 2

export function DailyBars({
  title,
  points,
  format,
}: {
  title: string
  points: Point[]
  format: (value: number) => string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const [asTable, setAsTable] = useState(false)
  const max = Math.max(...points.map((p) => p.value), 0)
  const width = 100 / Math.max(points.length, 1)
  const active = hover == null ? null : points[hover]

  return (
    <figure className="space-y-2">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">{title}</span>
        <button
          type="button"
          className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          aria-pressed={asTable}
          onClick={() => setAsTable(!asTable)}
        >
          {asTable ? "View as chart" : "View as table"}
        </button>
      </figcaption>
      {asTable ? (
        <div className="max-h-56 overflow-auto rounded-[4px] border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-card">
              <tr className="border-b text-left">
                <th className="px-3 py-1.5 font-medium">Day</th>
                <th className="px-3 py-1.5 text-right font-medium">{title}</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.label} className="border-b last:border-0">
                  <td className="px-3 py-1 text-muted-foreground">{p.label}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{format(p.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative" onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 100 ${HEIGHT}`} preserveAspectRatio="none" className="h-36 w-full" role="img" aria-label={title}>
            <line x1="0" x2="100" y1={HEIGHT - 0.5} y2={HEIGHT - 0.5} className="stroke-border" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            {points.map((p, i) => {
              const h = max ? (p.value / max) * (HEIGHT - 8) : 0
              return (
                <g key={p.label} onMouseEnter={() => setHover(i)}>
                  {/* Hit target: the whole column, bigger than the bar. */}
                  <rect x={i * width} y="0" width={width} height={HEIGHT} fill="transparent" />
                  {h > 0 && (
                    <rect
                      x={i * width + GAP / 4}
                      y={HEIGHT - h}
                      width={Math.max(width - GAP / 2, 0.2)}
                      height={h}
                      rx="0.6"
                      className={cn("fill-chart-1 transition-opacity", hover != null && hover !== i && "opacity-40")}
                    />
                  )}
                </g>
              )
            })}
          </svg>
          {active && (
            <div
              className="pointer-events-none absolute -top-2 rounded-[4px] border bg-card px-2 py-1 text-xs shadow-sm"
              style={{ left: `min(calc(${(hover! + 0.5) * width}% - 3rem), calc(100% - 6rem))` }}
            >
              <span className="text-muted-foreground">{active.label}</span>
              <span className="ml-2 font-semibold tabular-nums">{format(active.value)}</span>
            </div>
          )}
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>{points[0]?.label}</span>
            <span>{points[points.length - 1]?.label}</span>
          </div>
        </div>
      )}
    </figure>
  )
}

// A share of the largest value in a table column, drawn beside the number.
export function InlineBar({ value, max }: { value: number; max: number }) {
  const pct = max ? Math.max((value / max) * 100, value ? 2 : 0) : 0
  return (
    <span className="ml-2 inline-block h-1.5 w-16 overflow-hidden rounded-full bg-muted align-middle" aria-hidden>
      <span className="block h-full rounded-full bg-chart-1" style={{ width: `${pct}%` }} />
    </span>
  )
}

// Month-to-date spend against the cap, with the straight-line projection marked.
export function CapMeter({ spent, projected, cap }: { spent: number; projected: number; cap: number }) {
  const scale = Math.max(cap, projected, spent)
  const pct = (n: number) => `${Math.min((n / scale) * 100, 100)}%`
  return (
    <div className="space-y-1">
      <div className="relative h-3 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-chart-1" style={{ width: pct(spent) }} />
        <div className="absolute inset-y-0 w-0.5 bg-foreground" style={{ left: pct(cap) }} title="Monthly cap" />
        <div
          className="absolute inset-y-0 w-0.5 border-l-2 border-dashed border-muted-foreground"
          style={{ left: pct(projected) }}
          title="Projected by month end"
        />
      </div>
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
        <span>Spent so far (bar)</span>
        <span>Projected (dashed)</span>
        <span>Cap (solid line)</span>
      </div>
    </div>
  )
}

// A short list of labeled bars, each value written beside its bar.
export function HorizontalBars({
  title,
  rows,
  format = (v) => String(v),
}: {
  title: string
  rows: { key: string; label: string; value: number; detail?: string }[]
  format?: (value: number) => string
}) {
  const max = Math.max(...rows.map((r) => r.value), 0)
  return (
    <figure className="space-y-2">
      <figcaption className="text-sm font-semibold">{title}</figcaption>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing in this period.</p>
      ) : (
        <dl className="space-y-2">
          {rows.map((r) => (
            <div key={r.key} className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-3 text-sm">
              <dt className="truncate" title={r.label}>
                {r.label}
              </dt>
              <span aria-hidden className="h-2 overflow-hidden rounded-full bg-muted">
                <span className="block h-full rounded-full bg-chart-1" style={{ width: `${max ? Math.max((r.value / max) * 100, r.value ? 2 : 0) : 0}%` }} />
              </span>
              <dd className="text-right tabular-nums">
                {format(r.value)}
                {r.detail && <span className="block text-xs text-muted-foreground">{r.detail}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </figure>
  )
}
