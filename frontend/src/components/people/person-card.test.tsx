import { screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PersonCard } from "@/components/people/person-card"
import { renderWithRouter, violations } from "@/test/render"
import { row } from "@/test/fixtures"

const FOCUSABLE = "a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])"

describe("PersonCard", () => {
  it("is one link named by the person, with a decorative View", async () => {
    const { container } = renderWithRouter(<PersonCard row={row()} days={30} to="/analytics/people/monalisa" from="" />)
    const link = screen.getByRole("link", { name: "Mona Lisa" })
    expect(link).toHaveAttribute("href", "/analytics/people/monalisa")
    expect(container.querySelectorAll(FOCUSABLE)).toHaveLength(1)
    expect(screen.getByText("View")).toHaveAttribute("aria-hidden", "true")
    expect(container.querySelector("img")?.getAttribute("alt") ?? "").toBe("")
    expect(await violations(container)).toEqual([])
  })

  it("says what the numbers are, with roles and status as text", () => {
    const { container } = renderWithRouter(<PersonCard row={row()} days={30} to="/x" from="" />)
    const metrics = container.querySelector("dl")!
    expect(within(metrics).getByText("Reviews requested").nextSibling).toHaveTextContent("12")
    expect(within(metrics).getByText("Their PRs reviewed").nextSibling).toHaveTextContent("97 automatic")
    expect(within(metrics).getByText("Cost of requests").nextSibling).toHaveTextContent("$4.82")
    for (const text of ["Owner", "Portal admin", "Asks for reviews"]) expect(screen.getByText(text)).toBeInTheDocument()
  })

  it("shows a sentence instead of zeros for someone with no activity", () => {
    const { container } = renderWithRouter(
      <PersonCard
        row={row({ name: null, login: "octocat", activity_state: "none", requested: 0, prs_reviewed: 0, auto_reviews: 0, cost_triggered: 0, last_activity_at: "2026-03-04T10:00:00Z", in_org: false, org_role: null })}
        days={30}
        to="/x"
        from=""
      />,
    )
    expect(container.querySelector("dl")).toBeNull()
    expect(screen.getByText("No activity in the last 30 days · Last activity with Chakshu on Mar 4, 2026")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "octocat" })).toBeInTheDocument()
    expect(screen.getByText("Not in org")).toBeInTheDocument()
  })

  it("says when someone has never used Chakshu", () => {
    renderWithRouter(<PersonCard row={row({ activity_state: "none", last_activity_at: null })} days={30} to="/x" from="" />)
    expect(screen.getByText("Has not used Chakshu yet")).toBeInTheDocument()
  })
})
