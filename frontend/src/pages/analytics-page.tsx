import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { Link, Navigate, useSearchParams } from "react-router-dom"

import { CapMeter, DailyBars, InlineBar, StatTile } from "@/components/analytics-charts"
import { FilterBar, FilterSelect } from "@/components/analytics-filters"
import { ErrorNotice, Notice } from "@/components/notice"
import { RoiPanel } from "@/components/roi-panel"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  apiGet,
  apiPost,
  type AnalyticsRow,
  type CostView,
  type FindingRow,
  type Overview,
  type TeamsView,
} from "@/lib/api"
import { cost, count, percent, timeAgo } from "@/lib/format"
import { cn } from "@/lib/utils"

const PERIODS = [7, 30, 90, 180, 365]
const TABS = ["overview", "repos", "reviewers", "skills", "teams", "people", "cost", "findings"] as const
type Tab = (typeof TABS)[number]
const TAB_LABEL: Record<Tab, string> = {
  overview: "Overview",
  repos: "Repositories",
  reviewers: "Reviewers",
  skills: "Skills",
  teams: "Teams",
  people: "People",
  cost: "Cost",
  findings: "Findings",
}
const OUTCOME_SOURCE: Record<string, string> = {
  code_change: "code changed",
  thread_resolved: "thread resolved",
  reply: "decided in a reply",
}

// The URL holds the tab and filters, so a view can be shared and survives a reload.
function useFilters() {
  const [params, setParams] = useSearchParams()
  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }
  const set = (key: string, value: string | null) => update({ [key]: value })
  const days = Number(params.get("days") ?? 30)
  const query = new URLSearchParams({ days: String(days) })
  for (const key of ["repo_id", "reviewer", "trigger", "team"]) {
    const value = params.get(key)
    if (value) query.set(key, value)
  }
  return {
    tab: (TABS.includes(params.get("tab") as Tab) ? params.get("tab") : "overview") as Tab,
    days,
    repoId: params.get("repo_id"),
    reviewer: params.get("reviewer"),
    trigger: params.get("trigger"),
    team: params.get("team"),
    skill: params.get("skill"),
    outcome: params.get("outcome"),
    query: query.toString(),
    set,
    update,
  }
}

type Filters = ReturnType<typeof useFilters>

function AnalyticsFilterBar({ filters }: { filters: Filters }) {
  return (
    <FilterBar
      slice={filters}
      periods={PERIODS}
      onChange={(key, value) => filters.set(key, key === "days" && value === "30" ? null : value)}
    />
  )
}

function OverviewTab({ filters }: { filters: Filters }) {
  const data = useQuery({
    queryKey: ["analytics", "overview", filters.query],
    queryFn: () => apiGet<Overview>(`/api/analytics/overview?${filters.query}`),
  })
  if (data.error) return <ErrorNotice error={data.error} />
  if (!data.data) return null
  const t = data.data.tiles
  const label = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString("en", { month: "short", day: "numeric" })
  if (!t.reviews.value && !t.spend.value) {
    return <Notice>No reviews in this period. Widen the period or clear a filter.</Notice>
  }
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Reviews" value={count(t.reviews.value)} change={t.reviews.change} />
        <StatTile label="Pull requests reviewed" value={count(t.prs.value)} change={t.prs.change} />
        <StatTile label="Spend" value={cost(t.spend.value)} change={t.spend.change} />
        <StatTile label="Cost per fixed finding" value={cost(t.cost_per_fixed.value)} change={t.cost_per_fixed.change} hint="Nothing fixed yet in this period" />
        <StatTile label="Findings posted" value={count(t.posted.value)} change={t.posted.change} />
        <StatTile label="Findings fixed" value={count(t.fixed.value)} change={t.fixed.change} />
        <StatTile label="Fix rate" value={percent(t.fix_rate.value)} change={t.fix_rate.change} hint="Fixed out of fixed + dismissed" />
        <StatTile label="Asked for" value={percent(t.engaged_share.value)} change={t.engaged_share.change} hint="Share of reviews someone asked for" />
      </div>
      <Card>
        <CardContent className="grid gap-8 md:grid-cols-2">
          <DailyBars title="Reviews per day" points={data.data.daily.map((d) => ({ label: label(d.day), value: d.reviews }))} format={(v) => `${v} reviews`} />
          <DailyBars title="Spend per day" points={data.data.daily.map((d) => ({ label: label(d.day), value: d.spend }))} format={(v) => cost(v)} />
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        A review is a finished run that wasn't a reply. Spend includes failed runs. Fix rate leaves out findings with no
        verdict yet. Changes compare with the {filters.days} days before. Times are in UTC.
      </p>
    </div>
  )
}

function BreakdownTable({
  rows,
  name,
  onPick,
}: {
  rows: AnalyticsRow[]
  name: string
  onPick?: (key: string) => void
}) {
  const maxSpend = Math.max(...rows.map((r) => r.spend), 0)
  if (!rows.length) return <Notice>Nothing in this period.</Notice>
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{name}</TableHead>
            <TableHead className="text-right">Reviews</TableHead>
            <TableHead className="text-right">PRs</TableHead>
            <TableHead className="text-right">Spend</TableHead>
            <TableHead className="text-right">Posted</TableHead>
            <TableHead className="text-right">Fixed</TableHead>
            <TableHead className="text-right">Dismissed</TableHead>
            <TableHead className="text-right">Open</TableHead>
            <TableHead className="text-right">Fix rate</TableHead>
            <TableHead className="text-right">Cost per fix</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell className="font-medium">
                {onPick ? (
                  <button type="button" className="text-left hover:underline" onClick={() => onPick(r.key)}>
                    {r.key}
                  </button>
                ) : (
                  r.key
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">{count(r.reviews)}</TableCell>
              <TableCell className="text-right tabular-nums">{count(r.prs)}</TableCell>
              <TableCell className="whitespace-nowrap text-right tabular-nums">
                {cost(r.spend)}
                <InlineBar value={r.spend} max={maxSpend} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{count(r.posted)}</TableCell>
              <TableCell className="text-right tabular-nums">{count(r.fixed)}</TableCell>
              <TableCell className="text-right tabular-nums">{count(r.dismissed)}</TableCell>
              <TableCell className="text-right tabular-nums">{count(r.open)}</TableCell>
              <TableCell className="text-right tabular-nums">{percent(r.fix_rate)}</TableCell>
              <TableCell className="text-right tabular-nums">{cost(r.cost_per_fixed)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function BreakdownTab({ filters, by }: { filters: Filters; by: "repo" | "reviewer" | "skill" }) {
  const data = useQuery({
    queryKey: ["analytics", "breakdown", by, filters.query],
    queryFn: () => apiGet<AnalyticsRow[]>(`/api/analytics/breakdown?by=${by}&${filters.query}`),
  })
  const names = { repo: "Repository", reviewer: "Reviewer", skill: "Skill" }
  const pick =
    by === "reviewer"
      ? (key: string) => filters.set("reviewer", key)
      : by === "skill"
        ? (key: string) => filters.update({ skill: key, tab: "findings" })
        : undefined
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            {by === "skill" ? "Pick a skill to see its findings." : by === "reviewer" ? "Pick a reviewer to filter every view by it." : "Spend, outcomes and unit cost per repository."}
          </p>
          <a className={buttonVariants({ variant: "outline", size: "sm" })} href={`/api/analytics/breakdown.csv?by=${by}&${filters.query}`}>
            Export CSV
          </a>
        </div>
        <ErrorNotice error={data.error} />
        {data.data && <BreakdownTable rows={data.data} name={names[by]} onPick={pick} />}
      </CardContent>
    </Card>
  )
}

// A run counts for every team its author or requester was directly in at the time, so rows overlap.
function TeamsTab({ filters }: { filters: Filters }) {
  const queryClient = useQueryClient()
  const query = new URLSearchParams(filters.query)
  query.delete("team") // every team is a row here
  const data = useQuery({
    queryKey: ["analytics", "teams", query.toString()],
    queryFn: () => apiGet<TeamsView>(`/api/analytics/teams?${query}`),
  })
  const refresh = useMutation({
    mutationFn: () => apiPost("/api/analytics/teams/refresh"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["analytics"] }),
  })
  if (data.error) return <ErrorNotice error={data.error} />
  if (!data.data) return null
  const { rows, min_group, teams_source } = data.data
  const shown = rows.flatMap((r) => (r.hidden ? [] : [r]))
  const hidden = rows.length - shown.length
  const pick = (key: string) => {
    const team = shown.find((r) => r.key === key)
    if (team) filters.update({ team: String(team.team_id), tab: null })
  }
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">Pick a team to filter every view by it.</p>
          <Button variant="outline" size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            {refresh.isPending ? "Refreshing…" : "Refresh teams"}
          </Button>
        </div>
        <ErrorNotice error={refresh.error} />
        {teams_source.stale && (
          <Notice>
            GitHub couldn't be reached on the last team sync, so these teams are from{" "}
            {teams_source.synced_at ? timeAgo(teams_source.synced_at) : "an earlier sync"}.
          </Notice>
        )}
        {!teams_source.synced_at && !rows.length ? (
          <Notice>Teams haven't been synced from GitHub yet. They sync nightly, or refresh them now.</Notice>
        ) : (
          <BreakdownTable rows={shown} name="Team" onPick={pick} />
        )}
        {hidden > 0 && (
          <p className="text-sm text-muted-foreground">
            {hidden} team(s) hidden because fewer than {min_group} of their people appear in this slice.
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          A run counts for every team its PR author or requester was directly in when it ran, so team rows don't add up
          to the total. Members of child teams aren't counted in the parent. Runs from before the first team sync use
          the teams people were in at that sync.
        </p>
      </CardContent>
    </Card>
  )
}

function CostTab() {
  const data = useQuery({ queryKey: ["analytics", "cost"], queryFn: () => apiGet<CostView>("/api/analytics/cost") })
  if (data.error) return <ErrorNotice error={data.error} />
  if (!data.data) return null
  const { forecast, by, stopped_by_review_cap } = data.data
  const sections: [keyof CostView["by"], string][] = [
    ["repo", "Repository"],
    ["reviewer", "Reviewer"],
    ["model", "Model"],
    ["trigger", "Trigger"],
  ]
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label="Spent this month" value={cost(forecast.month_to_date)} hint="UTC calendar month" />
            <StatTile label="Projected by month end" value={cost(forecast.projected)} hint="At this month's daily rate" />
            <StatTile
              label="Monthly cap"
              value={forecast.cap == null ? "None" : cost(forecast.cap)}
              hint={forecast.cap_hit_on ? `Reached around ${new Date(forecast.cap_hit_on).toLocaleDateString("en", { month: "short", day: "numeric" })} at this rate` : forecast.cap == null ? "Set one in Settings" : "Not reached this month at this rate"}
            />
          </div>
          {forecast.cap != null && <CapMeter spent={forecast.month_to_date} projected={forecast.projected} cap={forecast.cap} />}
          {stopped_by_review_cap > 0 && (
            <p className="text-sm text-muted-foreground">
              {stopped_by_review_cap} review(s) this month stopped at the per-review cost cap.
            </p>
          )}
        </CardContent>
      </Card>
      <TokenMix rows={by.model} />
      {sections.map(([key, name]) => (
        <Card key={key}>
          <CardContent className="space-y-2">
            <h3 className="font-semibold">This month by {name.toLowerCase()}</h3>
            <BreakdownTable rows={by[key]} name={name} />
          </CardContent>
        </Card>
      ))}
      <RoiPanel query="days=30" />
    </div>
  )
}

// Where the tokens go, per model: bigger diffs show up as input, cached context as cache reads.
function TokenMix({ rows }: { rows: AnalyticsRow[] }) {
  const used = rows.filter((r) => r.input_tokens + r.output_tokens + r.cache_read_tokens + r.cache_write_tokens > 0)
  return (
    <Card>
      <CardContent className="space-y-2">
        <h3 className="font-semibold">Tokens this month by model</h3>
        {used.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No token counts yet. Runners report them from this version on; earlier reviews only have their cost.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Input</TableHead>
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead className="text-right">Cache reads</TableHead>
                  <TableHead className="text-right">Cache writes</TableHead>
                  <TableHead className="text-right">Spend</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {used.map((r) => (
                  <TableRow key={r.key}>
                    <TableCell className="font-medium">{r.key}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(r.input_tokens)}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(r.output_tokens)}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(r.cache_read_tokens)}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(r.cache_write_tokens)}</TableCell>
                    <TableCell className="text-right tabular-nums">{cost(r.spend)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function FindingsTab({ filters }: { filters: Filters }) {
  const extra = new URLSearchParams(filters.query)
  if (filters.skill) extra.set("skill", filters.skill)
  if (filters.outcome) extra.set("outcome", filters.outcome)
  const data = useQuery({
    queryKey: ["analytics", "findings", extra.toString()],
    queryFn: () => apiGet<FindingRow[]>(`/api/analytics/findings?${extra}`),
  })
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-4">
          <FilterSelect
            label="Outcome"
            value={filters.outcome}
            onChange={(v) => filters.set("outcome", v)}
            options={["open", "fixed", "dismissed"].map((o) => ({ value: o, label: o }))}
          />
          {filters.skill && (
            <Button size="sm" variant="outline" onClick={() => filters.set("skill", null)}>
              Skill: {filters.skill} ✕
            </Button>
          )}
          <span className="text-xs text-muted-foreground">Newest 200</span>
        </div>
        <ErrorNotice error={data.error} />
        {data.data?.length === 0 && <Notice>No findings match.</Notice>}
        {!!data.data?.length && (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Posted</TableHead>
                  <TableHead>Pull request</TableHead>
                  <TableHead>Reviewer · skill</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Outcome</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.data.map((f, i) => (
                  <TableRow key={`${f.posted_at}-${i}`}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{timeAgo(f.posted_at)}</TableCell>
                    <TableCell>
                      {f.review_url ? (
                        <a className="hover:underline" href={f.review_url} target="_blank" rel="noreferrer">
                          {f.repo}#{f.pr_number}
                        </a>
                      ) : (
                        `${f.repo}#${f.pr_number}`
                      )}
                      {f.pr_title && <span className="block max-w-xs truncate text-xs text-muted-foreground">{f.pr_title}</span>}
                    </TableCell>
                    <TableCell>
                      {f.reviewer}
                      {f.skill && <span className="text-muted-foreground"> · {f.skill}</span>}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{f.severity}</Badge> <span className="text-xs text-muted-foreground">{f.category}</span>
                    </TableCell>
                    <TableCell>
                      {f.outcome}
                      {f.outcome_source && <span className="block text-xs text-muted-foreground">{OUTCOME_SOURCE[f.outcome_source]}</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function peopleQuery(filters: Filters): string {
  const query = new URLSearchParams(filters.query)
  if (query.get("days") === "30") query.delete("days")
  return query.size ? `?${query}` : ""
}

export function AnalyticsPage() {
  const filters = useFilters()
  const tabs: Record<Tab, ReactNode> = {
    overview: <OverviewTab filters={filters} />,
    repos: <BreakdownTab filters={filters} by="repo" />,
    reviewers: <BreakdownTab filters={filters} by="reviewer" />,
    skills: <BreakdownTab filters={filters} by="skill" />,
    teams: <TeamsTab filters={filters} />,
    // The People view has its own page; carry the filters over.
    people: <Navigate to={`/analytics/people${peopleQuery(filters)}`} replace />,
    cost: <CostTab />,
    findings: <FindingsTab filters={filters} />,
  }
  return (
    <section className="space-y-5">
      <PageHeader eyebrow="Analytics" title="How Chakshu is used, and what it costs">
        Usage, outcomes and spend across your organization. For how a skill performs over time, see{" "}
        <Link className="text-brand-teal-ink hover:underline" to="/insights">
          Insights
        </Link>
        .
      </PageHeader>
      <nav className="flex flex-wrap gap-1 border-b" aria-label="Analytics views">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => filters.set("tab", tab === "overview" ? null : tab)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              filters.tab === tab ? "border-brand-teal text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {TAB_LABEL[tab]}
          </button>
        ))}
      </nav>
      {filters.tab !== "cost" && <AnalyticsFilterBar filters={filters} />}
      {tabs[filters.tab]}
    </section>
  )
}
