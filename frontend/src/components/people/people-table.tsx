import { Link } from "react-router-dom"

import { PersonAvatar } from "@/components/people/person-card"
import { RelativeDate } from "@/components/people/relative-date"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { DirectoryRow } from "@/lib/api"
import { cost, count } from "@/lib/format"
import { defaultOrder, roleBadge, SORT_LABEL, STATE_BADGE, type Order, type Sort } from "@/lib/people"

function SortHeader({
  sort,
  current,
  order,
  onSort,
  className,
}: {
  sort: Sort
  current: Sort
  order: Order
  onSort: (sort: Sort, order: Order) => void
  className?: string
}) {
  const active = sort === current
  const next: Order = active ? (order === "asc" ? "desc" : "asc") : defaultOrder(sort)
  return (
    <TableHead className={className} aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onSort(sort, next)}>
        {SORT_LABEL[sort]}
        <span aria-hidden="true" className="text-muted-foreground">
          {active ? (order === "asc" ? "↑" : "↓") : ""}
        </span>
      </button>
    </TableHead>
  )
}

// The same people as the cards, one row each. Sorting here sets the same URL params as the Sort menu.
export function PeopleTable({
  rows,
  sort,
  order,
  onSort,
  link,
  from,
}: {
  rows: DirectoryRow[]
  sort: Sort
  order: Order
  onSort: (sort: Sort, order: Order) => void
  link: (login: string) => string
  from: string
}) {
  const header = { current: sort, order, onSort }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortHeader sort="name" {...header} />
          <TableHead>Role</TableHead>
          <TableHead>Activity</TableHead>
          <SortHeader sort="requested" className="text-right" {...header} />
          <SortHeader sort="prs_reviewed" className="text-right" {...header} />
          <SortHeader sort="cost" className="text-right" {...header} />
          <SortHeader sort="last_activity" {...header} />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((p) => (
          <TableRow key={p.login}>
            <TableCell>
              <div className="flex max-w-64 items-center gap-2">
                <PersonAvatar row={p} className="size-7 text-xs" />
                <div className="min-w-0">
                  <Link
                    className="block truncate font-medium hover:underline"
                    to={link(p.login)}
                    state={{ from }}
                    title={p.name ?? p.login}
                  >
                    {p.name ?? p.login}
                  </Link>
                  {p.name && <span className="block truncate text-xs text-muted-foreground">@{p.login}</span>}
                </div>
              </div>
            </TableCell>
            <TableCell>
              {roleBadge(p)}
              {p.is_portal_admin && <span className="block text-xs text-muted-foreground">Portal admin</span>}
            </TableCell>
            <TableCell>
              <Badge variant="outline">{STATE_BADGE[p.activity_state]}</Badge>
            </TableCell>
            <TableCell className="text-right tabular-nums">{count(p.requested)}</TableCell>
            <TableCell className="text-right tabular-nums">
              {count(p.prs_reviewed)}
              {p.auto_reviews > 0 && <span className="block text-xs text-muted-foreground">{count(p.auto_reviews)} automatic</span>}
            </TableCell>
            <TableCell className="text-right tabular-nums">{cost(p.cost_triggered)}</TableCell>
            <TableCell className="whitespace-nowrap text-muted-foreground">
              {p.last_activity_at ? <RelativeDate iso={p.last_activity_at} /> : "Never"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
