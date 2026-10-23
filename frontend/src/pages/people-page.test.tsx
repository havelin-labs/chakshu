import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PeoplePage } from "@/pages/people-page"
import { directory, mockFetch } from "@/test/fixtures"
import { renderRoutes, violations } from "@/test/render"

const session = (admin: boolean) => ({
  configured: true,
  setup_claimed: false,
  app: null,
  webhooks: true,
  user: { login: "monalisa", name: "Mona Lisa", avatar_url: null, is_admin: admin },
  csrf_token: "t",
})

function start(url: string, { admin = true, people = directory() } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      mockFetch({
        "/api/session": session(admin),
        "/api/analytics/people": people,
        "/api/settings/analytics": { show_names: true, min_group: 5 },
        "/api/repos": [],
        "/api/reviewers": [],
      }),
    ),
  )
  return renderRoutes(
    [
      { path: "/analytics/people", element: <PeoplePage /> },
      { path: "/analytics/people/:login", element: <p>Person page</p> },
      { path: "/analytics/me", element: <p>My page</p> },
    ],
    url,
  )
}

describe("PeoplePage", () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it("lists people with a polite result count and no axe violations", async () => {
    const { container } = start("/analytics/people")
    expect(await screen.findByRole("link", { name: "Mona Lisa" })).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("2 people · 1 with no activity in the last 30 days")
    expect(screen.queryByText(/^#\d/)).toBeNull() // no rank numbers
    expect(screen.queryByText(/Sorted by/)).toBeNull()
    expect(await violations(container)).toEqual([])
  })

  it("keeps toolbar changes in the URL", async () => {
    const { router } = start("/analytics/people?days=90")
    await screen.findByRole("link", { name: "Mona Lisa" })
    await userEvent.click(screen.getByRole("button", { name: "Table" }))
    expect(router.state.location.search).toBe("?days=90&view=table")
    await userEvent.type(screen.getByRole("searchbox"), "mona")
    await waitFor(() => expect(router.state.location.search).toBe("?days=90&q=mona&view=table"))
    // Wait for the page to re-render with the search before sorting, as a person would.
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.map(([url]) => String(url))).toContain("/api/analytics/people?days=90&q=mona"),
    )
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "ascending")
    await userEvent.click(screen.getByRole("button", { name: /Cost of requests/ }))
    expect(router.state.location.search).toBe("?days=90&q=mona&sort=cost&view=table")
    expect(screen.getByText("Sorted by cost of requests, highest first")).toBeInTheDocument()
    const calls = vi.mocked(fetch).mock.calls.map(([url]) => String(url))
    expect(calls).toContain("/api/analytics/people?days=90&q=mona&sort=cost")
  })

  it("passes the directory query to the person page so Back can restore it", async () => {
    const { router } = start("/analytics/people?days=90&role=owner")
    await userEvent.click(await screen.findByRole("link", { name: "Mona Lisa" }))
    expect(router.state.location.pathname).toBe("/analytics/people/monalisa")
    expect(router.state.location.search).toBe("?days=90")
    expect(router.state.location.state).toEqual({ from: "?days=90&role=owner" })
  })

  it("shows why the directory is hidden", async () => {
    start("/analytics/people", { people: directory({ hidden: true, hidden_reason: "small_group", counts: null, rows: [], total: 0 }) })
    expect(await screen.findByText(/Fewer than 5 people used Chakshu/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Widen the period" })).toBeInTheDocument()
  })

  it("offers to clear filters when nobody matches", async () => {
    start("/analytics/people?q=zzz", { people: directory({ rows: [], total: 0 }) })
    expect(await screen.findByText("No one matches these filters.")).toBeInTheDocument()
  })

  it("sends people who aren't admins to their own page", async () => {
    start("/analytics/people", { admin: false })
    expect(await screen.findByText("My page")).toBeInTheDocument()
  })
})
