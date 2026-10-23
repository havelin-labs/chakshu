import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { HiddenState } from "@/components/people/hidden-state"

describe("HiddenState", () => {
  it("explains that names are off and links to the setting", () => {
    render(<HiddenState reason="names_off" minGroup={5} isAdmin />)
    expect(screen.getByText("Names are turned off for analytics. Individual usage isn't shown.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Open analytics settings" })).toHaveAttribute("href", "#privacy")
  })

  it("explains small groups and offers a wider period", () => {
    const widen = vi.fn()
    render(<HiddenState reason="small_group" minGroup={5} isAdmin onWiden={widen} />)
    expect(screen.getByText("Fewer than 5 people used Chakshu in this slice, so it's hidden for privacy.")).toBeInTheDocument()
    screen.getByRole("button", { name: "Widen the period" }).click()
    expect(widen).toHaveBeenCalled()
    expect(screen.getByRole("link", { name: "Privacy" })).toBeInTheDocument()
  })

  it("doesn't point people who aren't admins at settings", () => {
    render(<HiddenState reason="small_group" minGroup={5} isAdmin={false} />)
    expect(screen.queryByRole("link")).toBeNull()
  })
})
