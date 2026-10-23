import type { DirectoryRow, PeopleResult } from "@/lib/api"

export const row = (overrides: Partial<DirectoryRow> = {}): DirectoryRow => ({
  login: "monalisa",
  name: "Mona Lisa",
  avatar_url: null,
  org_role: "owner",
  in_org: true,
  is_portal_admin: true,
  last_login_at: "2026-10-20T08:00:00Z",
  activity_state: "engaged",
  requested: 12,
  prs_reviewed: 9,
  auto_reviews: 7,
  engaged: true,
  cost_triggered: 4.82,
  last_activity_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
  ...overrides,
})

export const directory = (overrides: Partial<PeopleResult> = {}): PeopleResult => ({
  hidden: false,
  hidden_reason: null,
  min_group: 5,
  period: { days: 30, from: "2026-09-23", to: "2026-10-23" },
  members_source: { synced_at: "2026-10-23T09:15:00Z", stale: false },
  total: 2,
  page: 1,
  page_size: 24,
  counts: { all: 2, engaged: 1, auto_only: 0, none: 1, not_in_org: 0 },
  rows: [
    row(),
    row({ login: "octocat", name: null, org_role: "member", is_portal_admin: false, activity_state: "none", requested: 0, prs_reviewed: 0, auto_reviews: 0, cost_triggered: 0, last_activity_at: null }),
  ],
  ...overrides,
})

// Serve canned JSON for fetch calls whose path starts with a key.
export function mockFetch(routes: Record<string, unknown>) {
  return async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost")
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.pathname.startsWith(k))
    const body = key ? routes[key] : {}
    return new Response(JSON.stringify(body), { status: key ? 200 : 404, headers: { "Content-Type": "application/json" } })
  }
}
