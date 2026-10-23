import type { ReactNode } from "react"
import { createBrowserRouter, RouterProvider } from "react-router-dom"

import { Layout } from "@/components/layout"
import { RequireUser } from "@/components/require-user"
import { AnalyticsPage } from "@/pages/analytics-page"
import { InsightsPage } from "@/pages/insights-page"
import { LoginPage } from "@/pages/login-page"
import { MyActivityPage } from "@/pages/my-activity-page"
import { RepoPage } from "@/pages/repo-page"
import { ReposPage } from "@/pages/repos-page"
import { ReviewerEditPage } from "@/pages/reviewer-edit-page"
import { ReviewersPage } from "@/pages/reviewers-page"
import { RunPage } from "@/pages/run-page"
import { RunsPage } from "@/pages/runs-page"
import { SettingsPage } from "@/pages/settings-page"
import { SetupInstalledPage } from "@/pages/setup-installed-page"
import { SetupPage } from "@/pages/setup-page"
import { StatusPage } from "@/pages/status-page"

const signedIn = (page: ReactNode, admin = false) => <RequireUser admin={admin}>{page}</RequireUser>

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: signedIn(<RunsPage />) },
      { path: "/runs/:id", element: signedIn(<RunPage />) },
      { path: "/repos", element: signedIn(<ReposPage />) },
      { path: "/repos/:id", element: signedIn(<RepoPage />) },
      { path: "/reviewers", element: signedIn(<ReviewersPage />) },
      { path: "/reviewers/new", element: signedIn(<ReviewerEditPage />) },
      { path: "/reviewers/:id/edit", element: signedIn(<ReviewerEditPage />) },
      { path: "/insights", element: signedIn(<InsightsPage />) },
      { path: "/analytics", element: signedIn(<AnalyticsPage />, true) },
      { path: "/me", element: signedIn(<MyActivityPage />) },
      { path: "/settings", element: signedIn(<SettingsPage />, true) },
      { path: "/status", element: signedIn(<StatusPage />) },
      { path: "/login", element: <LoginPage /> },
      { path: "/setup", element: <SetupPage /> },
      { path: "/setup/installed", element: <SetupInstalledPage /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
