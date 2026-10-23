import { EmptyState } from "@/components/people/empty-state"
import { RelativeDate } from "@/components/people/relative-date"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { usePersonActivity } from "@/hooks/use-people"
import { cost } from "@/lib/format"
import { ROLE_IN_RUN, type SliceParams } from "@/lib/people"

// The person's runs, newest first. More load only when asked, never on scroll.
export function RecentActivityList({ login, slice }: { login: string; slice: SliceParams }) {
  const activity = usePersonActivity(login, slice, true)
  const items = activity.data?.pages.flatMap((page) => page.items) ?? []
  if (activity.error && !items.length) {
    return (
      <EmptyState
        title="Activity could not be loaded."
        action={
          <Button size="sm" variant="outline" onClick={() => activity.refetch()}>
            Retry
          </Button>
        }
      />
    )
  }
  if (activity.isPending) return <p className="text-sm text-muted-foreground">Loading activity…</p>
  if (!items.length) return <p className="text-sm text-muted-foreground">No runs in this period.</p>
  return (
    <div className="space-y-3">
      <ul role="list" className="divide-y rounded-[4px] border bg-card">
        {items.map((item) => (
          <li key={item.run_id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 px-4 py-3 text-sm">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">{ROLE_IN_RUN[item.role]}</Badge>
                <span className="text-muted-foreground">{item.trigger.replace("_", " ")}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground">{item.reviewer}</span>
              </div>
              <p className="truncate">
                {item.review_url ? (
                  <a className="font-medium hover:underline" href={item.review_url} target="_blank" rel="noreferrer">
                    {item.repo}#{item.pr_number}
                  </a>
                ) : (
                  <span className="font-medium">
                    {item.repo}#{item.pr_number}
                  </span>
                )}
                {item.pr_title && <span className="text-muted-foreground"> {item.pr_title}</span>}
              </p>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <RelativeDate iso={item.created_at} />
              <span className="block">
                {item.status} · {cost(item.cost_usd)}
              </span>
            </div>
          </li>
        ))}
      </ul>
      {activity.error && <p className="text-sm text-destructive">Activity could not be loaded.</p>}
      {activity.hasNextPage && (
        <Button variant="outline" onClick={() => activity.fetchNextPage()} disabled={activity.isFetchingNextPage}>
          {activity.isFetchingNextPage ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  )
}
