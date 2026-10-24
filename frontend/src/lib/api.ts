// One place for talking to the Chakshu API, so every page handles errors and CSRF the same way.

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let csrfToken = ""

export function setCsrfToken(token: string) {
  csrfToken = token
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" }
  if (body !== undefined) headers["Content-Type"] = "application/json"
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken

  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : response.statusText
    throw new ApiError(response.status, detail)
  }
  return data as T
}

export const apiGet = <T>(path: string) => request<T>("GET", path)
export const apiPost = <T>(path: string, body: unknown = {}) => request<T>("POST", path, body)
export const apiPut = <T>(path: string, body: unknown = {}) => request<T>("PUT", path, body)
export const apiPatch = <T>(path: string, body: unknown = {}) => request<T>("PATCH", path, body)
export const apiDelete = <T>(path: string) => request<T>("DELETE", path)

export type ConnectorList = {
  kinds: Record<string, string>
  connectors: {
    name: string
    kind: string
    base_url: string
    username: string | null
    secret_hint: string
    enabled: boolean
  }[]
}

export type Health = { status: string; version: string }
export type Ready = { status: "ok" | "unavailable"; detail?: string }

export type User = { login: string; name: string | null; avatar_url: string | null; is_admin: boolean }

export type Reviewer = {
  id: string
  account: string
  name: string
  product: string | null
  description: string | null
  owner_team: string
  team: string // org/chakshu-<name>: request it in a PR's Reviewers box to run just this reviewer
  model: string | null
  repos: string[]
  paths: string[]
  auto: string[]
  skills: string[]
  fail_check_on: string | null
  source_sha: string
  source_url: string | null
  errors: string[]
}

export const SEVERITIES = ["info", "low", "medium", "high", "critical"] as const
export type Severity = (typeof SEVERITIES)[number]

export type SkillDraft = { name: string; description: string; body: string; extra: Record<string, unknown> }

export type ReviewerLimits = { max_usd?: number | null; max_findings?: number; min_severity?: Severity }

// A reviewer folder in editable form; saving it opens a pull request in the reviewers repo.
export type ReviewerDraft = {
  account: string
  name: string
  product: string | null
  description: string | null
  owner_team: string
  model: string | null
  repos: string[]
  paths: string[]
  auto: string[]
  connectors: string[]
  limits: ReviewerLimits
  fail_check_on: Severity | null
  tools: string[]
  rules: string
  skills: SkillDraft[]
  shared_skills: string[]
}

export type ReviewerOptions = {
  accounts: string[]
  models: string[]
  default_model: string | null
  connectors: string[]
  auto_events: string[]
}

export type ReviewerProposal = { url: string; number: number; created: boolean }

export type RunStatus = "queued" | "running" | "dispatched" | "succeeded" | "failed" | "cancelled"

// Still on its way to a result: queued here, being dispatched, or running in GitHub Actions.
export const isLive = (status: RunStatus) => status === "queued" || status === "running" || status === "dispatched"

export type Run = {
  id: string
  repo: string
  repo_id: string
  reviewer: string
  pr_number: number
  pr_title: string | null
  pr_url: string
  head_sha: string
  trigger: string
  requested_by: string | null
  status: RunStatus
  progress: string | null
  model: string | null
  cost_usd: number | null
  duration_ms: number | null
  review_url: string | null
  actions_run_url: string | null
  created_at: string
  finished_at: string | null
}

export type Finding = {
  path: string
  line: number
  severity: string
  category: string
  title: string
  body: string
  suggestion?: string
  skill?: string
}

export type ReviewResult = {
  summary: string
  findings: Finding[]
  posted: number
  summary_only: number
  repeats: number
  since?: string | null
  resolved?: number
}

// A reply run answered someone in one of Chakshu's review threads, and may have settled the finding.
export type ReplyResult = {
  reply: string
  outcome?: "open" | "fixed" | "dismissed"
  resolved?: boolean
  turns?: number | null
}

export type RunDetail = Run & {
  note: string | null
  error: string | null
  attempts: number
  result: ReviewResult | ReplyResult | null
}

export type Repo = { id: string; full_name: string; private: boolean; enabled: boolean }

export type Pull = {
  number: number
  title: string
  author: string | null
  draft: boolean
  head_sha: string
  updated_at: string
  url: string
}

export type ReviewOutcome = { queued: string[]; already: string[]; refused: string | null }

export type AdminSettings = {
  anthropic_api_key: { set: boolean; hint: string; from_env: boolean }
  claude_oauth_token: { set: boolean; hint: string; from_env: boolean }
  access: "api_key" | "subscription" | "environment" | "none"
  default_model: string
  max_usd_per_review: number
  monthly_cap_usd: number | null
  spend_this_month: number
  reviewers_repo: string
  actions_action: string
  actions_runs_on: string
  runner_url: string
  runner_public: boolean
  webhooks: { url: string; public: boolean; secret_set: boolean; events: string[] }
}

export type SkillStat = {
  account: string
  reviewer: string
  skill: string
  posted: number
  fixed: number
  dismissed: number
  open: number
  fix_rate: number | null
}

export type FailedEvent = {
  id: string
  event: string
  action: string | null
  repo: string | null
  attempts: number
  error: string | null
  received_at: string
}

export type Session = {
  configured: boolean
  setup_claimed: boolean
  app: { slug: string; install_url: string } | null
  webhooks: boolean
  user: User | null
  csrf_token: string
}

export type ActionsStatus = {
  workflow: "current" | "outdated" | "missing"
  proposal_url: string | null
  secrets: Record<string, boolean>
  runs_on: string[]
  runs_on_override: string | null
  ready: boolean
}

export type AppPermissions = {
  ok: boolean
  settings_url: string
  missing: string[]
  missing_events: string[]
  installations: { account: string; missing: string[]; missing_events: string[]; review_url: string }[]
}

export type SecretsSync = { synced: string[]; failed: Record<string, string> }
export type AnalyticsRow = {
  key: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reviews: number
  prs: number
  engaged: number
  spend: number
  cost_per_review: number | null
  posted: number
  fixed: number
  dismissed: number
  open: number
  fix_rate: number | null
  dismissed_rate: number | null
  cost_per_fixed: number | null
  engaged_share: number | null
}

export type TeamRow = { key: string; team_id: number; slug: string | null; org: string | null; deleted: boolean } & (
  | ({ hidden: false; people: number } & AnalyticsRow)
  | { hidden: true }
)

export type TeamsView = { min_group: number; teams_source: MembersSource; rows: TeamRow[] }

export type TeamOption = { id: number; org: string; slug: string; name: string; deleted: boolean }

export type SpeedMetric = { n: number; median_hours: number | null; p90_hours: number | null; small_sample: boolean }
export type SpeedCohort = { prs: number; first_review: SpeedMetric; merge: SpeedMetric }
export type SpeedRow = { repo_id: string; repo: string; reviewed: SpeedCohort; not_reviewed: SpeedCohort }
export type SpeedView = { small_sample: number; rows: SpeedRow[] }

export type Tile = { value: number | null; previous: number | null; change: number | null }

export type Overview = {
  tiles: Record<
    "reviews" | "prs" | "spend" | "posted" | "fixed" | "fix_rate" | "cost_per_fixed" | "engaged_share" | "requesters",
    Tile
  >
  daily: { day: string; reviews: number; spend: number; posted: number; fixed: number }[]
}

export type PersonRow = {
  login: string
  name: string | null
  requested: number
  prs_reviewed: number
  auto_reviews: number
  engaged: boolean
  cost_triggered: number
}

export type ActivityState = "engaged" | "auto_only" | "none"
export type HiddenReason = "names_off" | "small_group"

// One card in the People directory.
export type DirectoryRow = PersonRow & {
  avatar_url: string | null
  org_role: "owner" | "member" | null
  in_org: boolean
  is_portal_admin: boolean
  last_login_at: string | null
  activity_state: ActivityState
  last_activity_at: string | null
}

export type Period = { days: number; from: string; to: string }
export type MembersSource = { synced_at: string | null; stale: boolean }

export type PeopleResult = {
  hidden: boolean
  hidden_reason: HiddenReason | null
  min_group: number
  period: Period
  members_source: MembersSource
  total: number
  page: number
  page_size: number
  counts: Record<ActivityState | "all" | "not_in_org", number> | null
  rows: DirectoryRow[]
}

export type CostView = {
  forecast: { month_to_date: number; projected: number; cap: number | null; cap_hit_on: string | null }
  stopped_by_review_cap: number
  by: Record<"repo" | "reviewer" | "model" | "trigger", AnalyticsRow[]>
}

export type FindingRow = {
  posted_at: string
  repo: string
  pr_number: number
  pr_title: string | null
  review_url: string | null
  reviewer: string
  skill: string | null
  severity: string
  category: string
  outcome: "open" | "fixed" | "dismissed"
  outcome_source: "code_change" | "thread_resolved" | "reply" | null
}

export type AnalyticsPrivacy = {
  show_names: boolean
  min_group: number
  retention_days: number | null
  export_people: boolean
}

export type AuditRow = { at: string; user: string; action: string; target: string | null; details: Record<string, unknown> }
export type PersonTotals = {
  requested: number
  prs_reviewed: number
  auto_reviews: number
  replies: number
  self_requested_on_own_prs: number
  cost_triggered: number
  cost_on_own_prs: number
}

export type PersonProfile = {
  login: string
  name: string | null
  avatar_url: string | null
  org_role: "owner" | "member" | null
  in_org: boolean
  is_portal_admin: boolean
  last_login_at: string | null
  first_activity_at: string | null
  last_activity_at: string | null
  activity_state: ActivityState
  github_url: string
}

// One person's page. When hidden, only `person` (small groups) or nothing (names off) comes back.
export type PersonResult = {
  hidden: boolean
  hidden_reason: HiddenReason | null
  min_group: number
  is_self: boolean
  canonical_login?: string
  period: Period
  person?: PersonProfile
  totals?: PersonTotals
  previous_totals?: PersonTotals
  by_trigger?: { trigger: string; runs: number; cost_usd: number }[]
  by_repo?: { repo_id: string | null; repo: string; runs: number; prs: number; cost_usd: number }[]
  by_reviewer?: { reviewer: string; runs: number; cost_usd: number }[]
  daily?: { day: string; requested: number; own_prs_reviewed: number }[]
}

export type PersonActivityItem = {
  run_id: string
  created_at: string
  role: "requested" | "author" | "both"
  trigger: string
  repo: string
  repo_id: string
  pr_number: number
  pr_title: string | null
  reviewer: string
  status: RunStatus
  review_url: string | null
  cost_usd: number | null
}

export type PersonActivityPage = {
  hidden: boolean
  hidden_reason: HiddenReason | null
  items: PersonActivityItem[]
  next_cursor: string | null
}

export type RoiView = {
  assumptions: { minutes: Record<Severity, number>; hourly_rate: number | null }
  fixed_by_severity: Partial<Record<Severity, number>>
  spend: number
  estimate: { hours_saved: number; gross_value: number; net_value: number } | null
}
