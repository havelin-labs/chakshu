import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { StatTile } from "@/components/analytics-charts"
import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { apiGet, type PersonRow } from "@/lib/api"
import { cost, count } from "@/lib/format"

const PERIODS = [30, 90, 365]

// Each person sees exactly the row an admin sees about them on the People view.
export function MyActivityPage() {
  const [days, setDays] = useState(30)
  const me = useQuery({
    queryKey: ["analytics", "me", days],
    queryFn: () => apiGet<{ row: PersonRow | null }>(`/api/analytics/me?days=${days}`),
  })
  const row = me.data?.row

  return (
    <section className="space-y-5">
      <PageHeader
        eyebrow="My activity"
        title="What Chakshu has done for you"
        actions={
          <div className="flex gap-1">
            {PERIODS.map((d) => (
              <Button key={d} size="sm" variant={days === d ? "default" : "outline"} onClick={() => setDays(d)}>
                {d === 365 ? "1 year" : `${d} days`}
              </Button>
            ))}
          </div>
        }
      >
        This is the same information your organization's admins can see about you in Chakshu's analytics, and nothing
        more. It shows usage, not how good your work is.
      </PageHeader>
      <ErrorNotice error={me.error} />
      {me.data && !row && <Notice>No activity in this period.</Notice>}
      {row && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Reviews you asked for" value={count(row.requested)} hint={`Last ${days} days`} />
          <StatTile label="Your PRs reviewed" value={count(row.prs_reviewed)} hint={`Last ${days} days`} />
          <StatTile label="Of those, automatic" value={count(row.auto_reviews)} hint="Ran without anyone asking" />
          <StatTile label="Cost of reviews you asked for" value={cost(row.cost_triggered)} hint="Paid by your organization" />
        </div>
      )}
    </section>
  )
}
