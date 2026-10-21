import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom"

import { Layout } from "@/components/layout"
import { useSession } from "@/hooks/use-session"
import { SetupInstalledPage } from "@/pages/setup-installed-page"
import { SetupPage } from "@/pages/setup-page"
import { StatusPage } from "@/pages/status-page"

// Until GitHub is connected, every route leads to setup.
function Home() {
  const { data: session } = useSession()
  if (!session) return null
  if (!session.configured) return <Navigate to="/setup" replace />
  return <StatusPage />
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Home /> },
      { path: "/setup", element: <SetupPage /> },
      { path: "/setup/installed", element: <SetupInstalledPage /> },
      { path: "/status", element: <StatusPage /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
