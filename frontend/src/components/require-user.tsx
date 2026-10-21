import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"

import { Notice } from "@/components/notice"
import { useSession } from "@/hooks/use-session"

// Route guard: setup first, then sign-in, then (optionally) admin.
export function RequireUser({ admin = false, children }: { admin?: boolean; children: ReactNode }) {
  const { data: session } = useSession()
  if (!session) return null
  if (!session.configured) return <Navigate to="/setup" replace />
  if (!session.user) return <Navigate to="/login" replace />
  if (admin && !session.user.is_admin) return <Notice>Only Chakshu admins can open this page.</Notice>
  return children
}
