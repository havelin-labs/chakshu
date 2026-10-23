import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { PersonPage } from "@/pages/person-page"
import { activity, mockFetch, person } from "@/test/fixtures"
import { renderRoutes, violations } from "@/test/render"

function start(url: string, { admin = true, me = "admin", page = person() as unknown, state = undefined as unknown } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      mockFetch({
        "/api/session": { configured: true, setup_claimed: false, app: null, webhooks: true, csrf_token: "t", user: { login: me, name: null, avatar_url: null, is_admin: admin } },
        "/api/analytics/people/monalisa/activity": activity,
        "/api/analytics/people/": page,
        "/api/repos": [],
        "/api/reviewers": [],
      }),
    ),
  )
  const view = renderRoutes(
    [
      { path: "/analytics/people/:login", element: <PersonPage /> },
      { path: "/analytics/people", element: <p>Directory</p> },
    ],
    url,
    state,
  )
  return view
}

describe("PersonPage", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("shows usage with neutral comparisons and no quality numbers", async () => {
    const { container } = start("/analytics/people/monalisa")
    expect(await screen.findByRole("heading", { level: 1, name: "Mona Lisa" })).toHaveFocus()
    expect(screen.getByText("Reviews requested").parentElement).toHaveTextContent("In the last 30 days, up 4 from the previous 30 days")
    expect(screen.getByText("Cost of their requests").parentElement).toHaveTextContent("up $1.77")
    expect(screen.queryByText(/finding|severity|rank|score/i)).toBeNull()
    expect(screen.queryByText("This is what admins see about you.", { exact: false })).toBeNull()
    expect(await screen.findByRole("link", { name: "acme/api#7" })).toHaveAttribute("target", "_blank")
    expect(screen.getByRole("button", { name: "Load more" })).toBeInTheDocument()
    expect(await violations(container)).toEqual([])
  })

  it("renders the daily numbers as a table on request", async () => {
    start("/analytics/people/monalisa")
    const chart = (await screen.findByText("Reviews requested per day")).closest("figure")!
    await userEvent.click(within(chart).getByRole("button", { name: "View as table" }))
    const rows = within(chart).getAllByRole("row")
    expect(rows).toHaveLength(3) // header and two days
    expect(rows[1]).toHaveTextContent("Oct 22")
    expect(rows[1]).toHaveTextContent("2")
  })

  it("speaks to the person in self mode", async () => {
    start("/analytics/people/monalisa", { admin: false, me: "monalisa", page: person({ is_self: true }) })
    expect(await screen.findByRole("heading", { level: 1, name: "Your Chakshu activity" })).toBeInTheDocument()
    expect(screen.getByText(/This is what admins see about you/)).toBeInTheDocument()
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).toBeNull()
  })

  it("goes back to the directory with its filters", async () => {
    start("/analytics/people/monalisa", { state: { from: "?role=owner&q=mo" } })
    const crumb = await screen.findByRole("link", { name: "People" })
    expect(crumb).toHaveAttribute("href", "/analytics/people?role=owner&q=mo")
  })

  it("switches the URL to GitHub's spelling of the login", async () => {
    const { router } = start("/analytics/people/MONALISA", { page: person({ canonical_login: "monalisa" }) })
    await screen.findByRole("heading", { level: 1, name: "Mona Lisa" })
    expect(router.state.location.pathname).toBe("/analytics/people/monalisa")
  })

  it("explains someone who never used Chakshu", async () => {
    const page = person()
    start("/analytics/people/monalisa", { page: { ...page, person: { ...page.person, last_activity_at: null } } })
    expect(await screen.findByText("Mona Lisa hasn't used Chakshu yet.")).toBeInTheDocument()
  })

  it("explains a hidden page", async () => {
    start("/analytics/people/monalisa", { page: person({ hidden: true, hidden_reason: "small_group", totals: undefined }) })
    expect(await screen.findByText(/Fewer than 5 people used Chakshu/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/analytics/people#privacy")
  })
})
