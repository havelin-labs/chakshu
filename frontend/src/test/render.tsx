import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render } from "@testing-library/react"
import axe from "axe-core"
import type { ReactNode } from "react"
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom"

export function renderRoutes(routes: RouteObject[], url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [url] })
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...view, router }
}

export function renderWithRouter(ui: ReactNode, url = "/") {
  return renderRoutes([{ path: "*", element: ui }], url)
}

// axe violations, ignoring color contrast (jsdom has no layout or computed colors to check it with).
export async function violations(container: Element) {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } })
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(", ")}`)
}
