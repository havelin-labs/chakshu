import type { ReactNode } from "react"
import { createBrowserRouter, RouterProvider } from "react-router-dom"

import { Layout } from "@/components/layout"
import { RequireUser } from "@/components/require-user"
import { LoginPage } from "@/pages/login-page"
import { ReviewersPage } from "@/pages/reviewers-page"
import { SetupInstalledPage } from "@/pages/setup-installed-page"
import { SetupPage } from "@/pages/setup-page"
import { StatusPage } from "@/pages/status-page"

const signedIn = (page: ReactNode, admin = false) => <RequireUser admin={admin}>{page}</RequireUser>

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: signedIn(<StatusPage />) },
      { path: "/login", element: <LoginPage /> },
      { path: "/setup", element: <SetupPage /> },
      { path: "/setup/installed", element: <SetupInstalledPage /> },
      { path: "/reviewers", element: signedIn(<ReviewersPage />) },
      { path: "/status", element: signedIn(<StatusPage />) },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
