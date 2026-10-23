import { useEffect, useRef } from "react"
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom"

import { DailyBars, HorizontalBars } from "@/components/analytics-charts"
import { FilterBar, type SliceKey } from "@/components/analytics-filters"
import { Notice } from "@/components/notice"
import { EmptyState } from "@/components/people/empty-state"
import { HiddenState } from "@/components/people/hidden-state"
import { KpiTiles } from "@/components/people/kpi-tiles"
import { PersonAvatar } from "@/components/people/person-card"
import { RecentActivityList } from "@/components/people/recent-activity"
import { RelativeDate } from "@/components/people/relative-date"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { usePerson } from "@/hooks/use-people"
import { useSession } from "@/hooks/use-session"
import { ApiError, type PersonResult } from "@/lib/api"
import { cost, count } from "@/lib/format"
import { PERIODS, periodText, readSlice, roleBadge, sliceQuery, STATE_BADGE, type SliceParams } from "@/lib/people"

function Breakdowns({ data }: { data: PersonResult }) {
  return (
    <Card>
      <CardContent className="grid gap-8 md:grid-cols-3">
        <HorizontalBars
          title="Runs by trigger"
          rows={(data.by_trigger ?? []).map((r) => ({ key: r.trigger, label: r.trigger.replace("_", " "), value: r.runs, detail: cost(r.cost_usd) }))}
          format={count}
        />
        <HorizontalBars
          title="Runs by repository"
          rows={(data.by_repo ?? []).map((r) => ({ key: r.repo_id ?? "other", label: r.repo, value: r.runs, detail: `${r.prs} ${r.prs === 1 ? "PR" : "PRs"} · ${cost(r.cost_usd)}` }))}
          format={count}
        />
        <HorizontalBars
          title="Runs by reviewer"
          rows={(data.by_reviewer ?? []).map((r) => ({ key: r.reviewer, label: r.reviewer, value: r.runs, detail: cost(r.cost_usd) }))}
          format={count}
        />
      </CardContent>
    </Card>
  )
}

function Usage({ data, slice, onWiden }: { data: PersonResult; slice: SliceParams; onWiden: () => void }) {
  const person = data.person!
  const display = person.name ?? person.login
  if (!person.last_activity_at) {
    return (
      <EmptyState
        title={`${display} hasn't used Chakshu yet.`}
        reason="Reviews they request or reviews of their PRs will show up here."
      />
    )
  }
  const totals = data.totals!
  const empty = Object.values(totals).every((v) => v === 0)
  const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en", { month: "short", day: "numeric" })
  return (
    <div className="space-y-6">
      <KpiTiles totals={totals} previous={data.previous_totals!} days={slice.days} />
      {empty ? (
        <EmptyState
          title={`No activity in ${periodText(slice.days)}.`}
          action={
            slice.days < 90 && (
              <Button size="sm" variant="outline" onClick={onWiden}>
                Show last 90 days
              </Button>
            )
          }
        />
      ) : (
        <>
          <Card>
            <CardContent className="grid gap-8 md:grid-cols-2">
              <DailyBars
                title="Reviews requested per day"
                points={data.daily!.map((d) => ({ label: day(d.day), value: d.requested }))}
                format={(v) => `${v} requested`}
              />
              <DailyBars
                title="Their PRs reviewed per day"
                points={data.daily!.map((d) => ({ label: day(d.day), value: d.own_prs_reviewed }))}
                format={(v) => `${v} PRs`}
              />
            </CardContent>
          </Card>
          <Breakdowns data={data} />
        </>
      )}
      <section className="space-y-3">
        <h2 className="font-heading text-xl font-bold">Recent activity</h2>
        <RecentActivityList login={person.login} slice={slice} />
      </section>
      <p className="text-xs text-muted-foreground">
        Counts cover {periodText(slice.days)} and compare with the same length of time before. Reviews they requested on
        their own PRs: {count(totals.self_requested_on_own_prs)}. Days are in UTC.
      </p>
    </div>
  )
}

// One person's usage of Chakshu. Admins can open anyone; everyone else sees their own page in self mode.
export function PersonPage() {
  const { login = "" } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { data: session } = useSession()
  const slice = readSlice(searchParams)
  const person = usePerson(login, slice)
  const heading = useRef<HTMLHeadingElement>(null)
  const data = person.data
  const isAdmin = Boolean(session?.user?.is_admin)
  const isSelf = data?.is_self ?? login.toLowerCase() === session?.user?.login.toLowerCase()

  // The URL uses GitHub's spelling of the login.
  useEffect(() => {
    if (data?.canonical_login && data.canonical_login !== login) {
      navigate(`/analytics/people/${encodeURIComponent(data.canonical_login)}${location.search}`, { replace: true, state: location.state })
    }
  }, [data?.canonical_login, login, location.search, location.state, navigate])

  // On arriving from another page, move focus to the page's heading.
  const loaded = Boolean(data)
  useEffect(() => {
    heading.current?.focus()
  }, [login, loaded])

  const setSlice = (key: SliceKey, value: string | null) => {
    const next = { ...slice, [key]: key === "days" ? Number(value) : value }
    setSearchParams(new URLSearchParams(sliceQuery(next)), { replace: true })
  }
  const widen = () => setSlice("days", "90")
  const from = (location.state as { from?: string } | null)?.from
  const back = `/analytics/people${from ?? (slice.days !== 30 ? `?days=${slice.days}` : "")}`
  const display = data?.person ? (data.person.name ?? data.person.login) : login

  if (person.error instanceof ApiError && person.error.status === 403) return <Navigate to="/analytics/me" replace />
  return (
    <section className="space-y-6">
      {isAdmin && (
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink render={<Link to={back} />}>People</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{display}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      )}
      {person.error instanceof ApiError && person.error.status === 404 ? (
        <>
          <h1 ref={heading} tabIndex={-1} className="text-4xl font-bold tracking-tight outline-none">
            Person not found
          </h1>
          <EmptyState
            title={`No one with the login ${login} is in this org or in Chakshu's history.`}
            action={
              isAdmin && (
                <Link className={buttonVariants({ variant: "outline", size: "sm" })} to={back}>
                  Back to People
                </Link>
              )
            }
          />
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-4">
            {data?.person && <PersonAvatar row={data.person} className="size-14 text-lg" />}
            <div className="min-w-0 space-y-1">
              <h1 ref={heading} tabIndex={-1} className="text-3xl font-bold tracking-tight break-words outline-none sm:text-4xl">
                {isSelf ? "Your Chakshu activity" : display}
              </h1>
              {data?.person && (
                <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <a className="hover:underline" href={data.person.github_url} target="_blank" rel="noreferrer">
                    @{data.person.login}
                  </a>
                  <Badge variant="secondary">{roleBadge(data.person)}</Badge>
                  {data.person.is_portal_admin && <Badge variant="outline">Portal admin</Badge>}
                  <Badge variant="outline">{STATE_BADGE[data.person.activity_state]}</Badge>
                  {data.person.last_activity_at && (
                    <span>
                      Last activity with Chakshu <RelativeDate iso={data.person.last_activity_at} />
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
          {isSelf && <Notice>This is what admins see about you. It shows usage, not how good your work is.</Notice>}
          <FilterBar slice={{ days: slice.days, repoId: slice.repo_id, reviewer: slice.reviewer, trigger: slice.trigger }} periods={PERIODS} onChange={setSlice} />
          {person.error && (
            <EmptyState
              title="Activity could not be loaded."
              action={
                <Button size="sm" variant="outline" onClick={() => person.refetch()}>
                  Retry
                </Button>
              }
            />
          )}
          {data?.hidden_reason && (
            <HiddenState
              reason={data.hidden_reason}
              minGroup={data.min_group}
              isAdmin={isAdmin}
              settingsHref="/analytics/people#privacy"
              onWiden={slice.days < PERIODS[PERIODS.length - 1] ? () => setSlice("days", "365") : undefined}
            />
          )}
          {data && !data.hidden && data.person && <Usage data={data} slice={slice} onWiden={widen} />}
        </>
      )}
    </section>
  )
}

// /analytics/me: the signed-in person's own page.
export function MyPage() {
  const { data: session } = useSession()
  const location = useLocation()
  if (!session?.user) return null
  return <Navigate to={`/analytics/people/${encodeURIComponent(session.user.login)}${location.search}`} replace />
}
