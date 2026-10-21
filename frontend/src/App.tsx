import { createBrowserRouter, RouterProvider } from "react-router-dom"

import { Layout } from "@/components/layout"
import { StatusPage } from "@/pages/status-page"

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [{ path: "/", element: <StatusPage /> }],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
