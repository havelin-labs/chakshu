import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { StatTile } from "@/components/analytics-charts"
import { ErrorNotice, Notice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPut, type RoiView, type Severity } from "@/lib/api"
import { cost, count } from "@/lib/format"

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"]
type Draft = { minutes: Record<Severity, number>; hourly_rate: number | null }

// An estimate, labelled as one: fixed findings (measured) valued with the admin's own assumptions.
export function RoiPanel({ query }: { query: string }) {
  const queryClient = useQueryClient()
  const data = useQuery({ queryKey: ["analytics", "roi", query], queryFn: () => apiGet<RoiView>(`/api/analytics/roi?${query}`) })
  // Unsaved edits, on top of what the server has.
  const [draft, setDraft] = useState<Draft | null>(null)
  const form: Draft | null = draft ?? (data.data ? data.data.assumptions : null)
  const save = useMutation({
    mutationFn: (body: Draft) => apiPut("/api/settings/analytics/roi", body),
    onSuccess: () => {
      setDraft(null)
      queryClient.invalidateQueries({ queryKey: ["analytics", "roi"] })
    },
  })
  if (data.error) return <ErrorNotice error={data.error} />
  if (!data.data || !form) return null
  const { fixed_by_severity: fixed, spend, estimate } = data.data

  return (
    <Card>
      <CardContent className="space-y-4">
        <div>
          <h3 className="font-semibold">Return on spend (estimate)</h3>
          <p className="text-sm text-muted-foreground">
            The fixed findings and spend are measured. What a fix is worth is your assumption: minutes of review work a
            fixed finding saves, and what an hour costs. No study gives one right number, so treat this as a rough guide.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <StatTile
            label="Hours saved (est.)"
            value={estimate ? String(estimate.hours_saved) : "Not set"}
            hint={`${count(Object.values(fixed).reduce((a, b) => a + (b ?? 0), 0))} findings fixed`}
          />
          <StatTile label="Value (est.)" value={estimate ? cost(estimate.gross_value) : "Not set"} hint="Hours saved × hourly rate" />
          <StatTile
            label="Net of spend (est.)"
            value={estimate ? cost(estimate.net_value) : "Not set"}
            hint={`Spend in period ${cost(spend)}`}
          />
        </div>
        {!estimate && <Notice>Set an hourly rate below to see the estimate.</Notice>}
        <form
          className="grid gap-3 sm:grid-cols-6"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(form)
          }}
        >
          {SEVERITIES.map((s) => (
            <div key={s} className="space-y-1">
              <Label htmlFor={`roi-${s}`}>
                {s} <span className="text-muted-foreground">({count(fixed[s] ?? 0)} fixed)</span>
              </Label>
              <Input
                id={`roi-${s}`}
                type="number"
                min={0}
                max={600}
                value={form.minutes[s]}
                onChange={(e) => setDraft({ ...form, minutes: { ...form.minutes, [s]: Number(e.target.value) } })}
                aria-describedby="roi-minutes-help"
              />
            </div>
          ))}
          <div className="space-y-1">
            <Label htmlFor="roi-rate">Hourly rate ($)</Label>
            <Input
              id="roi-rate"
              type="number"
              min={0}
              max={10000}
              value={form.hourly_rate ?? ""}
              placeholder="e.g. 60"
              onChange={(e) => setDraft({ ...form, hourly_rate: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </div>
          <p id="roi-minutes-help" className="text-xs text-muted-foreground sm:col-span-5">
            Minutes saved per fixed finding, by severity.
          </p>
          <Button type="submit" size="sm" disabled={save.isPending} className="sm:col-span-1">
            {save.isPending ? "Saving…" : "Save assumptions"}
          </Button>
        </form>
        <ErrorNotice error={save.error} />
      </CardContent>
    </Card>
  )
}
