// URL state and wording for the People directory and person pages. No React here, so it's easy to test.

import type { ActivityState, DirectoryRow } from "@/lib/api"
import { timeAgo } from "@/lib/format"

export const PERIODS = [7, 30, 90, 180, 365] as const
export const PAGE_SIZES = [24, 48, 96] as const
export const SORTS = ["name", "last_activity", "requested", "prs_reviewed", "cost"] as const
export const ROLES = ["all", "owner", "member"] as const
export const ACTIVITIES = ["all", "engaged", "auto_only", "none", "not_in_org"] as const
export const VIEWS = ["grid", "table"] as const

export type Sort = (typeof SORTS)[number]
export type Order = "asc" | "desc"
export type View = (typeof VIEWS)[number]

// Filters shared by every analytics view, carried from the directory to a person's page.
export type SliceParams = { days: number; repo_id: string | null; reviewer: string | null; trigger: string | null }

export type DirectoryParams = SliceParams & {
  q: string
  role: (typeof ROLES)[number]
  activity: (typeof ACTIVITIES)[number]
  sort: Sort
  order: Order
  view: View | null // null: not in the URL, so the remembered choice applies
  page: number
  page_size: (typeof PAGE_SIZES)[number]
}

export const defaultOrder = (sort: Sort): Order => (sort === "name" ? "asc" : "desc")

export const DEFAULTS: DirectoryParams = {
  days: 30,
  repo_id: null,
  reviewer: null,
  trigger: null,
  q: "",
  role: "all",
  activity: "all",
  sort: "name",
  order: "asc",
  view: null,
  page: 1,
  page_size: 24,
}

function pick<T extends readonly (string | number)[]>(options: T, raw: string | null, fallback: T[number]): T[number] {
  const found = options.find((o) => String(o) === raw)
  return found ?? fallback
}

export function readSlice(search: URLSearchParams): SliceParams {
  return {
    days: Number(pick(PERIODS as readonly number[], search.get("days"), DEFAULTS.days)),
    repo_id: search.get("repo_id"),
    reviewer: search.get("reviewer"),
    trigger: search.get("trigger"),
  }
}

export function readParams(search: URLSearchParams): DirectoryParams {
  const sort = pick(SORTS, search.get("sort"), DEFAULTS.sort)
  const page = Number.parseInt(search.get("page") ?? "", 10)
  return {
    ...readSlice(search),
    q: search.get("q") ?? "",
    role: pick(ROLES, search.get("role"), DEFAULTS.role),
    activity: pick(ACTIVITIES, search.get("activity"), DEFAULTS.activity),
    sort,
    order: pick(["asc", "desc"] as const, search.get("order"), defaultOrder(sort)),
    view: (VIEWS as readonly string[]).includes(search.get("view") ?? "") ? (search.get("view") as View) : null,
    page: page > 0 ? page : 1,
    page_size: Number(pick(PAGE_SIZES, search.get("page_size"), DEFAULTS.page_size)) as DirectoryParams["page_size"],
  }
}

// The URL for these params, leaving out every value that is the default.
export function writeParams(params: DirectoryParams): URLSearchParams {
  const out = new URLSearchParams()
  const defaults = { ...DEFAULTS, order: defaultOrder(params.sort) }
  for (const key of Object.keys(DEFAULTS) as (keyof DirectoryParams)[]) {
    const value = params[key]
    if (value === null || value === "" || value === defaults[key]) continue
    out.set(key, String(value))
  }
  return out
}

// What the API needs: everything but the view, with defaults left to the server.
export function apiQuery(params: DirectoryParams): string {
  const query = writeParams({ ...params, view: null })
  return query.toString()
}

export function sliceQuery(slice: SliceParams): string {
  const out = new URLSearchParams()
  if (slice.days !== DEFAULTS.days) out.set("days", String(slice.days))
  for (const key of ["repo_id", "reviewer", "trigger"] as const) {
    if (slice[key]) out.set(key, slice[key])
  }
  return out.toString()
}

export const hasFilters = (p: DirectoryParams) =>
  Boolean(p.q || p.role !== "all" || p.activity !== "all" || p.repo_id || p.reviewer || p.trigger)

export const SORT_LABEL: Record<Sort, string> = {
  name: "Name",
  last_activity: "Last activity",
  requested: "Reviews requested",
  prs_reviewed: "Their PRs reviewed",
  cost: "Cost of requests",
}

// Shown only when the list isn't in name order, so nobody reads a position as a rank.
export function sortLabel(sort: Sort, order: Order): string | null {
  if (sort === "name") return null
  const direction =
    sort === "last_activity"
      ? order === "desc"
        ? "most recent first"
        : "least recent first"
      : order === "desc"
        ? "highest first"
        : "lowest first"
  return `Sorted by ${SORT_LABEL[sort].toLowerCase()}, ${direction}`
}

export const ROLE_LABEL: Record<(typeof ROLES)[number], string> = { all: "All roles", owner: "Owners", member: "Members" }

export const ACTIVITY_LABEL: Record<(typeof ACTIVITIES)[number], string> = {
  all: "Everyone in the org",
  engaged: "Asks for reviews",
  auto_only: "Automatic reviews only",
  none: "No activity",
  not_in_org: "Not in the org",
}

export const STATE_BADGE: Record<ActivityState, string> = {
  engaged: "Asks for reviews",
  auto_only: "Automatic reviews only",
  none: "No activity",
}

export function roleBadge(row: Pick<DirectoryRow, "in_org" | "org_role">): string {
  if (!row.in_org) return "Not in org"
  return row.org_role === "owner" ? "Owner" : "Member"
}

export function initials(name: string | null, login: string): string {
  const words = (name ?? login).trim().split(/\s+/).filter(Boolean)
  const letters = words.length > 1 ? words[0][0] + words[words.length - 1][0] : (words[0] ?? login).slice(0, 2)
  return letters.toUpperCase()
}

export const periodText = (days: number) => (days === 365 ? "the last year" : `the last ${days} days`)

const absolute = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" })
export const formatDay = (iso: string) => absolute.format(new Date(iso))

const RELATIVE_FOR = 30 * 86_400_000

// "3 days ago" within a month of now, "on Mar 4, 2026" after.
export function relativeText(iso: string, now = Date.now()): string {
  return now - new Date(iso).getTime() < RELATIVE_FOR ? timeAgo(iso) : `on ${formatDay(iso)}`
}

export function noActivityText(row: Pick<DirectoryRow, "last_activity_at">, days: number): string {
  if (!row.last_activity_at) return "Has not used Chakshu yet"
  return `No activity in ${periodText(days)} · Last activity with Chakshu on ${formatDay(row.last_activity_at)}`
}

// The pages to offer: the first, the last, and one either side of the current one.
export function pageList(current: number, total: number): (number | "gap")[] {
  const pages: (number | "gap")[] = []
  for (let n = 1; n <= total; n++) {
    if (n === 1 || n === total || Math.abs(n - current) <= 1) pages.push(n)
    else if (pages[pages.length - 1] !== "gap") pages.push("gap")
  }
  return pages
}
