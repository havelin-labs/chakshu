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

export type Session = {
  configured: boolean
  setup_claimed: boolean
  app: { slug: string; install_url: string } | null
  webhooks: boolean
  user: User | null
  csrf_token: string
}
