import type { DirectoryRow, PeopleResult, PersonResult } from "@/lib/api"

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

export const person = (overrides: Partial<PersonResult> = {}): PersonResult => {
  const totals = { requested: 12, prs_reviewed: 9, auto_reviews: 7, replies: 3, self_requested_on_own_prs: 2, cost_triggered: 4.82, cost_on_own_prs: 6.1 }
  return {
    hidden: false,
    hidden_reason: null,
    min_group: 5,
    is_self: false,
    period: { days: 30, from: "2026-09-23", to: "2026-10-23" },
    person: {
      login: "monalisa",
      name: "Mona Lisa",
      avatar_url: null,
      org_role: "owner",
      in_org: true,
      is_portal_admin: true,
      last_login_at: null,
      first_activity_at: "2025-11-02T10:00:00Z",
      last_activity_at: new Date(Date.now() - 86_400_000).toISOString(),
      activity_state: "engaged",
      github_url: "https://github.com/monalisa",
    },
    totals,
    previous_totals: { ...totals, requested: 8, cost_triggered: 3.05 },
    by_trigger: [{ trigger: "mention", runs: 6, cost_usd: 2.1 }],
    by_repo: [{ repo_id: "r1", repo: "acme/api", runs: 10, prs: 6, cost_usd: 3.9 }],
    by_reviewer: [{ reviewer: "security", runs: 5, cost_usd: 1.7 }],
    daily: [
      { day: "2026-10-22", requested: 2, own_prs_reviewed: 1 },
      { day: "2026-10-23", requested: 0, own_prs_reviewed: 3 },
    ],
    ...overrides,
  }
}

export const activity = {
  hidden: false,
  hidden_reason: null,
  items: [
    { run_id: "1", created_at: "2026-10-21T14:03:00Z", role: "requested", trigger: "mention", repo: "acme/api", repo_id: "r1", pr_number: 7, pr_title: "Fix the thing", reviewer: "security", status: "succeeded", review_url: "https://github.com/acme/api/pull/7", cost_usd: 0.4 },
  ],
  next_cursor: "abc",
}
