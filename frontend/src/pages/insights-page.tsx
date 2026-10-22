import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorNotice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiGet, type SkillStat } from "@/lib/api"

const PERIODS = [30, 90, 365]

function FixRate({ rate }: { rate: number | null }) {
  if (rate == null) return <span className="text-muted-foreground">—</span>
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <span className="block h-full bg-primary" style={{ width: `${Math.round(rate * 100)}%` }} />
      </span>
      {Math.round(rate * 100)}%
    </span>
  )
}

export function InsightsPage() {
  const [days, setDays] = useState(90)
  const stats = useQuery({
    queryKey: ["skill-stats", days],
    queryFn: () => apiGet<SkillStat[]>(`/api/stats/skills?days=${days}`),
  })

  return (
    <section>
      <PageHeader
        eyebrow="Insights"
        title="Which skills earn their keep"
        actions={
          <div className="flex gap-1">
            {PERIODS.map((period) => (
              <Button
                key={period}
                size="sm"
                variant={period === days ? "default" : "outline"}
                onClick={() => setDays(period)}
              >
                {period} days
              </Button>
            ))}
          </div>
        }
      >
        Inline findings per skill and what happened to them. Fixed: the code changed and the thread was resolved.
        Dismissed: someone resolved the thread without changing the code. A skill with a low fix rate is probably
        noisy; tighten it or drop it.
      </PageHeader>
      <ErrorNotice error={stats.error} />
      <Card>
        <CardContent>
          {stats.data?.length === 0 ? (
            <p className="py-6 text-sm text-muted-foreground">
              No findings in this period yet. Outcomes appear after Chakshu reviews a PR again.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Reviewer</TableHead>
                  <TableHead>Skill</TableHead>
                  <TableHead className="text-right">Posted</TableHead>
                  <TableHead className="text-right">Fixed</TableHead>
                  <TableHead className="text-right">Dismissed</TableHead>
                  <TableHead className="text-right">Open</TableHead>
                  <TableHead>Fix rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.data?.map((s) => (
                  <TableRow key={`${s.account}/${s.reviewer}/${s.skill}`}>
                    <TableCell className="font-mono text-xs">{s.reviewer}</TableCell>
                    <TableCell className="font-mono text-xs">{s.skill}</TableCell>
                    <TableCell className="text-right">{s.posted}</TableCell>
                    <TableCell className="text-right">{s.fixed}</TableCell>
                    <TableCell className="text-right">{s.dismissed}</TableCell>
                    <TableCell className="text-right">{s.open}</TableCell>
                    <TableCell>
                      <FixRate rate={s.fix_rate} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
