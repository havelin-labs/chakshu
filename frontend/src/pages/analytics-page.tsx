import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"
import { Link, useSearchParams } from "react-router-dom"

import { CapMeter, DailyBars, InlineBar, StatTile } from "@/components/analytics-charts"
import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  apiGet,
  apiPatch,
  type AnalyticsPrivacy,
  type AnalyticsRow,
  type CostView,
  type FindingRow,
  type Overview,
  type PeopleResult,
  type Repo,
  type Reviewer,
} from "@/lib/api"
import { cost, count, percent, timeAgo } from "@/lib/format"
import { cn } from "@/lib/utils"

const PERIODS = [7, 30, 90, 365]
const TABS = ["overview", "repos", "reviewers", "skills", "people", "cost", "findings"] as const
type Tab = (typeof TABS)[number]
const TAB_LABEL: Record<Tab, string> = {
  overview: "Overview",
  repos: "Repositories",
  reviewers: "Reviewers",
  skills: "Skills",
  people: "People",
  cost: "Cost",
  findings: "Findings",
}
const TRIGGERS = ["mention", "review_requested", "portal", "auto", "reply"]
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
  for (const key of ["repo_id", "reviewer", "trigger"]) {
    const value = params.get(key)
    if (value) query.set(key, value)
  }
  return {
    tab: (TABS.includes(params.get("tab") as Tab) ? params.get("tab") : "overview") as Tab,
    days,
    repoId: params.get("repo_id"),
    reviewer: params.get("reviewer"),
    trigger: params.get("trigger"),
    skill: params.get("skill"),
    outcome: params.get("outcome"),
    query: query.toString(),
    set,
    update,
  }
}

type Filters = ReturnType<typeof useFilters>

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string | null
  onChange: (value: string | null) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <select
        className="h-8 rounded-[4px] border bg-background px-2 text-sm"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function FilterBar({ filters }: { filters: Filters }) {
  const repos = useQuery({ queryKey: ["repos"], queryFn: () => apiGet<Repo[]>("/api/repos") })
  const reviewers = useQuery({ queryKey: ["reviewers"], queryFn: () => apiGet<Reviewer[]>("/api/reviewers") })
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <div className="flex gap-1" role="group" aria-label="Period">
        {PERIODS.map((d) => (
          <Button key={d} size="sm" variant={filters.days === d ? "default" : "outline"} onClick={() => filters.set("days", String(d))}>
            {d === 365 ? "1 year" : `${d} days`}
          </Button>
        ))}
      </div>
      <Select
        label="Repository"
        value={filters.repoId}
        onChange={(v) => filters.set("repo_id", v)}
        options={(repos.data ?? []).map((r) => ({ value: r.id, label: r.full_name }))}
      />
      <Select
        label="Reviewer"
        value={filters.reviewer}
        onChange={(v) => filters.set("reviewer", v)}
        options={[...new Set((reviewers.data ?? []).map((r) => r.name))].map((n) => ({ value: n, label: n }))}
      />
      <Select
        label="Trigger"
        value={filters.trigger}
        onChange={(v) => filters.set("trigger", v)}
        options={TRIGGERS.map((t) => ({ value: t, label: t.replace("_", " ") }))}
      />
    </div>
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

function PrivacyCard() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ["analytics-privacy"], queryFn: () => apiGet<AnalyticsPrivacy>("/api/settings/analytics") })
  // Unsaved edits, on top of what the server has.
  const [draft, setForm] = useState<AnalyticsPrivacy | null>(null)
  const form = draft ?? settings.data
  const save = useMutation({
    mutationFn: (body: AnalyticsPrivacy) => apiPatch<AnalyticsPrivacy>("/api/settings/analytics", body),
    onSuccess: () => {
      setForm(null)
      queryClient.invalidateQueries({ queryKey: ["analytics-privacy"] })
      queryClient.invalidateQueries({ queryKey: ["analytics"] })
    },
  })
  if (!form) return null
  return (
    <Card>
      <CardContent className="space-y-3">
        <h3 className="font-semibold">Privacy</h3>
        <div className="flex flex-wrap items-end gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.show_names} onChange={(e) => setForm({ ...form, show_names: e.target.checked })} />
            Show people by name
          </label>
          <div className="space-y-1">
            <Label htmlFor="min-group">Smallest group shown</Label>
            <Input
              id="min-group"
              type="number"
              min={1}
              max={100}
              className="w-24"
              value={form.min_group}
              onChange={(e) => setForm({ ...form, min_group: Number(e.target.value) })}
            />
          </div>
          <Button size="sm" onClick={() => save.mutate(form)} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        <ErrorNotice error={save.error} />
        <p className="text-xs text-muted-foreground">
          Turn names off where a works council or employee agreement asks for it. Slices covering fewer people than the
          smallest group size are hidden, so a filter can't single someone out; 1 turns this off, otherwise use 3 to
          100. Every view and export of named people is logged.
        </p>
      </CardContent>
    </Card>
  )
}

function PeopleTab({ filters }: { filters: Filters }) {
  const data = useQuery({
    queryKey: ["analytics", "people", filters.query],
    queryFn: () => apiGet<PeopleResult>(`/api/analytics/people?${filters.query}&page_size=96`),
  })
  const result = data.data
  return (
    <div className="space-y-4">
      <PrivacyCard />
      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="max-w-2xl text-sm text-muted-foreground">
              Who uses Chakshu and what it costs, for enablement and budgeting. It isn't a measure of anyone's work:
              there are no findings per author and no ranking. Everyone can see their own row under My activity.
            </p>
            {result?.rows.length ? (
              <a className={buttonVariants({ variant: "outline", size: "sm" })} href={`/api/analytics/people.csv?${filters.query}`}>
                Export CSV
              </a>
            ) : null}
          </div>
          <ErrorNotice error={data.error} />
          {result?.hidden_reason === "names_off" && <Notice>Names are turned off for analytics.</Notice>}
          {result?.hidden_reason === "small_group" && (
            <Notice>Fewer than {result.min_group} people in this selection, so it's hidden for privacy.</Notice>
          )}
          {result && !result.hidden && result.rows.length === 0 && <Notice>Nobody used Chakshu in this period.</Notice>}
          {result && result.rows.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Person</TableHead>
                    <TableHead className="text-right">Reviews asked for</TableHead>
                    <TableHead className="text-right">Their PRs reviewed</TableHead>
                    <TableHead className="text-right">Of those, automatic</TableHead>
                    <TableHead className="text-right">Cost of reviews they asked for</TableHead>
                    <TableHead>Uses Chakshu</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.rows.map((p) => (
                    <TableRow key={p.login}>
                      <TableCell>
                        <span className="font-medium">{p.name ?? p.login}</span>
                        {p.name && <span className="ml-2 text-xs text-muted-foreground">@{p.login}</span>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{count(p.requested)}</TableCell>
                      <TableCell className="text-right tabular-nums">{count(p.prs_reviewed)}</TableCell>
                      <TableCell className="text-right tabular-nums">{count(p.auto_reviews)}</TableCell>
                      <TableCell className="text-right tabular-nums">{cost(p.cost_triggered)}</TableCell>
                      <TableCell>{p.engaged ? "asks for reviews" : "automatic only"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
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
      {sections.map(([key, name]) => (
        <Card key={key}>
          <CardContent className="space-y-2">
            <h3 className="font-semibold">This month by {name.toLowerCase()}</h3>
            <BreakdownTable rows={by[key]} name={name} />
          </CardContent>
        </Card>
      ))}
    </div>
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
          <Select
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

export function AnalyticsPage() {
  const filters = useFilters()
  const tabs: Record<Tab, ReactNode> = {
    overview: <OverviewTab filters={filters} />,
    repos: <BreakdownTab filters={filters} by="repo" />,
    reviewers: <BreakdownTab filters={filters} by="reviewer" />,
    skills: <BreakdownTab filters={filters} by="skill" />,
    people: <PeopleTab filters={filters} />,
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
      {filters.tab !== "cost" && <FilterBar filters={filters} />}
      {tabs[filters.tab]}
    </section>
  )
}
