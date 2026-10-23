import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { RelativeDate } from "@/components/people/relative-date"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { DirectoryRow } from "@/lib/api"
import { cost, count } from "@/lib/format"
import { initials, noActivityText, roleBadge, STATE_BADGE } from "@/lib/people"
import { cn } from "@/lib/utils"

export function PersonAvatar({ row, className }: { row: Pick<DirectoryRow, "avatar_url" | "name" | "login">; className?: string }) {
  return (
    <Avatar className={className}>
      {row.avatar_url && <AvatarImage src={row.avatar_url} alt="" />}
      <AvatarFallback aria-hidden="true">{initials(row.name, row.login)}</AvatarFallback>
    </Avatar>
  )
}

// One person in the directory. The whole card is the heading link (one tab stop); "View" only looks like a button.
export function PersonCard({
  row,
  days,
  to,
  from,
}: {
  row: DirectoryRow
  days: number
  to: string
  from: string
}) {
  const display = row.name ?? row.login
  return (
    <Card className="relative h-full min-h-72 transition-[box-shadow,translate] focus-within:ring-2 focus-within:ring-ring motion-safe:hover:-translate-y-0.5 motion-safe:hover:shadow-md">
      <div className="flex items-start gap-3 px-(--card-spacing)">
        <PersonAvatar row={row} className="size-11 shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          {/* Names wrap instead of being cut off; the card height absorbs a second line. */}
          <h3 className="font-heading text-base leading-snug font-semibold break-words">
            <Link to={to} state={{ from }} className="after:absolute after:inset-0 focus-visible:outline-none">
              {display}
            </Link>
          </h3>
          <p className="text-sm break-all text-muted-foreground">@{row.login}</p>
          <div className="flex flex-wrap gap-1 pt-1">
            <Badge variant="secondary">{roleBadge(row)}</Badge>
            {row.is_portal_admin && <Badge variant="outline">Portal admin</Badge>}
          </div>
        </div>
      </div>
      <CardContent className="flex-1 space-y-3">
        <Badge variant="outline">{STATE_BADGE[row.activity_state]}</Badge>
        {row.activity_state === "none" ? (
          <p className="text-sm text-muted-foreground">{noActivityText(row, days)}</p>
        ) : (
          <dl className="grid grid-cols-3 gap-2 tabular-nums">
            <div>
              <dt className="text-xs text-muted-foreground">Reviews requested</dt>
              <dd className="font-heading text-lg font-semibold">{count(row.requested)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Their PRs reviewed</dt>
              <dd className="font-heading text-lg font-semibold">
                {count(row.prs_reviewed)}
                {row.auto_reviews > 0 && (
                  <span className="block text-xs font-normal text-muted-foreground">{count(row.auto_reviews)} automatic</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Cost of requests</dt>
              <dd className="font-heading text-lg font-semibold">{cost(row.cost_triggered)}</dd>
            </div>
          </dl>
        )}
      </CardContent>
      <CardFooter className="justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {row.last_activity_at ? (
            <>
              Last activity with Chakshu <RelativeDate iso={row.last_activity_at} plain />
            </>
          ) : (
            "No activity with Chakshu yet"
          )}
        </span>
        <span aria-hidden="true" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "shrink-0")}>
          View
        </span>
      </CardFooter>
    </Card>
  )
}

export function PersonCardSkeleton() {
  return (
    <Card className="h-full min-h-72" aria-hidden="true">
      <CardHeader className="grid-cols-[auto_1fr] gap-x-3">
        <Skeleton className="row-span-2 size-10 rounded-full" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-20" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-10 w-full" />
      </CardContent>
    </Card>
  )
}

export function PersonCardGrid({ children }: { children: ReactNode }) {
  return (
    <ul role="list" className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {children}
    </ul>
  )
}
