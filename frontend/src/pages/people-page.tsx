import { useEffect, useRef, useState } from "react"
import { Navigate, useLocation, useSearchParams } from "react-router-dom"

import { AnalyticsPrivacyCard } from "@/components/analytics-privacy-card"
import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { EmptyState } from "@/components/people/empty-state"
import { HiddenState } from "@/components/people/hidden-state"
import { PeopleTable } from "@/components/people/people-table"
import { PeopleToolbar } from "@/components/people/people-toolbar"
import { PersonCard, PersonCardGrid, PersonCardSkeleton } from "@/components/people/person-card"
import { Button } from "@/components/ui/button"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { usePeopleDirectory, useRefreshMembers } from "@/hooks/use-people"
import { useSession } from "@/hooks/use-session"
import type { PeopleResult } from "@/lib/api"
import { timeAgo } from "@/lib/format"
import {
  defaultOrder,
  DEFAULTS,
  pageList,
  PERIODS,
  periodText,
  readParams,
  sliceQuery,
  writeParams,
  type DirectoryParams,
  type View,
} from "@/lib/people"

const VIEW_KEY = "chakshu.people.view"

function storedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "table" ? "table" : "grid"
  } catch {
    return "grid"
  }
}

function rememberView(view: View) {
  try {
    localStorage.setItem(VIEW_KEY, view)
  } catch {
    // Private windows can refuse storage; the URL still holds the choice.
  }
}

function resultText(result: PeopleResult, params: DirectoryParams): string {
  const people = `${result.total} ${result.total === 1 ? "person" : "people"}`
  if (params.activity !== "all" || !result.counts) return people
  return `${people} · ${result.counts.none} with no activity in ${periodText(params.days)}`
}

function Pages({ page, total, onPage }: { page: number; total: number; onPage: (page: number) => void }) {
  if (total <= 1) return null
  return (
    <Pagination>
      <PaginationContent>
        <PaginationItem>
          <PaginationPrevious disabled={page <= 1} onClick={() => onPage(page - 1)} />
        </PaginationItem>
        {pageList(page, total).map((n, i) => (
          <PaginationItem key={n === "gap" ? `gap-${i}` : n}>
            {n === "gap" ? (
              <PaginationEllipsis />
            ) : (
              <PaginationLink isActive={n === page} aria-label={`Page ${n}`} onClick={() => onPage(n)}>
                {n}
              </PaginationLink>
            )}
          </PaginationItem>
        ))}
        <PaginationItem>
          <PaginationNext disabled={page >= total} onClick={() => onPage(page + 1)} />
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )
}

function StaleNote({ syncedAt }: { syncedAt: string | null }) {
  const refresh = useRefreshMembers()
  return (
    <Notice>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          {syncedAt ? `Member list last updated ${timeAgo(syncedAt)}.` : "The member list hasn't been loaded yet."} GitHub
          couldn't be reached.
        </span>
        <Button size="sm" variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? "Refreshing…" : "Refresh members"}
        </Button>
      </div>
      <ErrorNotice error={refresh.error} />
    </Notice>
  )
}

function Directory() {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const params = readParams(searchParams)
  const view = params.view ?? storedView()
  const directory = usePeopleDirectory(params)
  const refresh = useRefreshMembers()
  const [search, setSearch] = useState(params.q)

  const searchTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(searchTimer.current), [])

  // Changes apply to the URL as it is when they land, so a delayed search can't undo another filter.
  const update = (changes: Partial<DirectoryParams>) => {
    setSearchParams(
      (current) => {
        const next = { ...readParams(current), ...changes }
        if (!("page" in changes)) next.page = 1
        if ("sort" in changes && !("order" in changes)) next.order = defaultOrder(next.sort)
        return writeParams(next)
      },
      { replace: true },
    )
  }

  // Search waits for typing to pause, so the audit log gets one row per search rather than per key.
  const onSearch = (text: string) => {
    setSearch(text)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => update({ q: text.trim() }), 300)
  }

  const clear = () => {
    clearTimeout(searchTimer.current)
    setSearch("")
    update({ ...DEFAULTS, days: params.days, sort: params.sort, order: params.order, view: params.view, page_size: params.page_size })
  }
  const widen = () => {
    const wider = PERIODS.find((d) => d > params.days)
    update({ days: wider ?? params.days, repo_id: null, reviewer: null, trigger: null })
  }
  const link = (login: string) => {
    const query = sliceQuery(params)
    return `/analytics/people/${encodeURIComponent(login)}${query ? `?${query}` : ""}`
  }

  const result = directory.data
  const pages = result ? Math.ceil(result.total / result.page_size) : 0
  return (
    <div className="space-y-5">
      <PeopleToolbar
        params={params}
        view={view}
        search={search}
        counts={result?.counts ?? null}
        onSearch={onSearch}
        onChange={update}
        onSlice={(key, value) => update({ [key]: key === "days" ? Number(value) : value } as Partial<DirectoryParams>)}
        onView={(next) => {
          rememberView(next)
          update({ view: next, page: params.page })
        }}
        onClear={clear}
      />
      {result?.members_source.stale && <StaleNote syncedAt={result.members_source.synced_at} />}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {result && !result.hidden ? resultText(result, params) : ""}
        </p>
        {result?.members_source && !result.members_source.stale && (
          <Button size="sm" variant="ghost" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? "Refreshing…" : "Refresh members"}
          </Button>
        )}
      </div>
      <ErrorNotice error={refresh.error} />
      {directory.error && (
        <EmptyState
          title="People could not be loaded."
          reason={directory.error instanceof Error ? directory.error.message : undefined}
          action={
            <Button size="sm" variant="outline" onClick={() => directory.refetch()}>
              Retry
            </Button>
          }
        />
      )}
      {!result && !directory.error && (
        <PersonCardGrid>
          {Array.from({ length: 8 }, (_, i) => (
            <li key={i}>
              <PersonCardSkeleton />
            </li>
          ))}
        </PersonCardGrid>
      )}
      {result?.hidden_reason && (
        <HiddenState
          reason={result.hidden_reason}
          minGroup={result.min_group}
          isAdmin
          onWiden={params.days < PERIODS[PERIODS.length - 1] || params.repo_id || params.reviewer || params.trigger ? widen : undefined}
        />
      )}
      {result && !result.hidden && result.rows.length === 0 && (
        <EmptyState
          title="No one matches these filters."
          action={
            <Button size="sm" variant="outline" onClick={clear}>
              Clear filters
            </Button>
          }
        />
      )}
      {result && result.rows.length > 0 && (
        <div className={directory.isPlaceholderData ? "opacity-60 transition-opacity" : undefined}>
          <h2 className="sr-only">People</h2>
          {view === "grid" ? (
            <PersonCardGrid>
              {result.rows.map((row) => (
                <li key={row.login}>
                  <PersonCard row={row} days={params.days} to={link(row.login)} from={location.search} />
                </li>
              ))}
            </PersonCardGrid>
          ) : (
            <PeopleTable
              rows={result.rows}
              sort={params.sort}
              order={params.order}
              onSort={(sort, order) => update({ sort, order })}
              link={link}
              from={location.search}
            />
          )}
        </div>
      )}
      {result && !result.hidden && <Pages page={params.page} total={pages} onPage={(page) => update({ page })} />}
    </div>
  )
}

// Everyone in the org as a card, with what they used Chakshu for. Admins only; others see their own page.
export function PeoplePage() {
  const { data: session } = useSession()
  if (!session?.user) return null
  if (!session.user.is_admin) return <Navigate to="/analytics/me" replace />
  return (
    <section className="space-y-8">
      <PageHeader eyebrow="Analytics · People" title="Who uses Chakshu">
        Everyone in your organization, with the reviews they asked for, their pull requests Chakshu reviewed, and what
        that cost. It's for enablement and budgeting, not a measure of anyone's work: there are no findings per person
        and no ranking. Everyone can see their own page.
      </PageHeader>
      <Directory />
      <AnalyticsPrivacyCard />
    </section>
  )
}
