import { useQuery } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { apiGet, type Repo, type Reviewer, type TeamOption } from "@/lib/api"

const TRIGGERS = ["mention", "review_requested", "portal", "auto", "reply"]

export function FilterSelect({
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

// `team` is left out where a view doesn't offer the team filter.
export type Slice = {
  days: number
  repoId: string | null
  reviewer: string | null
  trigger: string | null
  team?: string | null
}
export type SliceKey = "days" | "repo_id" | "reviewer" | "trigger" | "team"

// Period, repository, reviewer, trigger and team: the filters the analytics views share.
export function FilterBar({
  slice,
  periods,
  onChange,
}: {
  slice: Slice
  periods: readonly number[]
  onChange: (key: SliceKey, value: string | null) => void
}) {
  const repos = useQuery({ queryKey: ["repos"], queryFn: () => apiGet<Repo[]>("/api/repos") })
  const reviewers = useQuery({ queryKey: ["reviewers"], queryFn: () => apiGet<Reviewer[]>("/api/reviewers") })
  const withTeams = slice.team !== undefined
  const teams = useQuery({
    queryKey: ["analytics", "team-options"],
    queryFn: () => apiGet<TeamOption[]>("/api/analytics/teams/options"),
    enabled: withTeams,
  })
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <div className="flex flex-wrap gap-1" role="group" aria-label="Period">
        {periods.map((d) => (
          <Button
            key={d}
            size="sm"
            variant={slice.days === d ? "default" : "outline"}
            aria-pressed={slice.days === d}
            onClick={() => onChange("days", String(d))}
          >
            {d === 365 ? "1 year" : `${d} days`}
          </Button>
        ))}
      </div>
      <FilterSelect
        label="Repository"
        value={slice.repoId}
        onChange={(v) => onChange("repo_id", v)}
        options={(repos.data ?? []).map((r) => ({ value: r.id, label: r.full_name }))}
      />
      <FilterSelect
        label="Reviewer"
        value={slice.reviewer}
        onChange={(v) => onChange("reviewer", v)}
        options={[...new Set((reviewers.data ?? []).map((r) => r.name))].map((n) => ({ value: n, label: n }))}
      />
      <FilterSelect
        label="Trigger"
        value={slice.trigger}
        onChange={(v) => onChange("trigger", v)}
        options={TRIGGERS.map((t) => ({ value: t, label: t.replace("_", " ") }))}
      />
      {withTeams && (
        <FilterSelect
          label="Team"
          value={slice.team ?? null}
          onChange={(v) => onChange("team", v)}
          options={(teams.data ?? []).map((t) => ({
            value: String(t.id),
            label: `${t.org}/${t.slug}${t.deleted ? " (deleted)" : ""}`,
          }))}
        />
      )}
    </div>
  )
}
