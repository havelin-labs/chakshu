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

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled"

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

export type RunDetail = Run & {
  note: string | null
  error: string | null
  attempts: number
  result: {
    summary: string
    findings: Finding[]
    posted: number
    summary_only: number
    repeats: number
    since?: string | null
    resolved?: number
  } | null
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
  default_model: string
  max_usd_per_review: number
  monthly_cap_usd: number | null
  spend_this_month: number
  reviewers_repo: string
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
