import { useMutation, useQueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { apiPost, type User } from "@/lib/api"

export function UserMenu({ user }: { user: User }) {
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: () => apiPost("/api/auth/logout"),
    onSuccess: () => {
      queryClient.clear()
      window.location.assign("/login")
    },
  })

  return (
    <div className="flex items-center gap-3">
      {user.avatar_url && <img src={user.avatar_url} alt="" className="size-7 rounded-full border" />}
      <span className="hidden text-sm font-medium md:inline">{user.login}</span>
      <Button variant="outline" size="sm" onClick={() => logout.mutate()} disabled={logout.isPending}>
        Sign out
      </Button>
    </div>
  )
}
