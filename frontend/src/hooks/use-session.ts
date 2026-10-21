import { useQuery } from "@tanstack/react-query"

import { apiGet, setCsrfToken, type Session } from "@/lib/api"

export const SESSION_KEY = ["session"] as const

export function useSession() {
  return useQuery({
    queryKey: SESSION_KEY,
    queryFn: async () => {
      const session = await apiGet<Session>("/api/session")
      setCsrfToken(session.csrf_token)
      return session
    },
    staleTime: 60_000,
  })
}
