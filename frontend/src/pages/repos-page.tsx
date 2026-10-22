import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useSession } from "@/hooks/use-session"
import { apiGet, apiPost, apiPut, type Repo } from "@/lib/api"

export function ReposPage() {
  const { data: session } = useSession()
  const queryClient = useQueryClient()
  const repos = useQuery({ queryKey: ["repos"], queryFn: () => apiGet<Repo[]>("/api/repos") })
  const toggle = useMutation({
    mutationFn: (repo: Repo) => apiPut(`/api/repos/${repo.id}`, { enabled: !repo.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["repos"] }),
  })
  const sync = useMutation({
    mutationFn: () => apiPost("/api/repos/sync"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["repos"] }),
  })
  const isAdmin = Boolean(session?.user?.is_admin)
  const installUrl = session?.app?.install_url

  return (
    <section>
      <PageHeader
        eyebrow="Repositories"
        title="Repositories Chakshu can see"
        actions={
          isAdmin && (
            <div className="flex flex-wrap gap-2">
              {installUrl && (
                <a className={buttonVariants({ variant: "outline" })} href={installUrl} target="_blank" rel="noreferrer">
                  Change repository access
                </a>
              )}
              <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
                {sync.isPending ? "Syncing…" : "Sync repositories"}
              </Button>
            </div>
          )
        }
      >
        These come from the GitHub App installation. Open one to review a pull request from here.
      </PageHeader>
      <div className="space-y-4">
        <ErrorNotice error={repos.error ?? toggle.error ?? sync.error} />
        {repos.data?.length === 0 && (
          <Notice>
            No repositories yet. Use <b>Change repository access</b> to give the Chakshu app some repositories on
            GitHub, then press <b>Sync repositories</b>.
          </Notice>
        )}
        <Card>
          <CardContent className="divide-y">
            {repos.data?.map((repo) => (
              <div key={repo.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="flex items-center gap-2">
                  <Link to={`/repos/${repo.id}`} className="font-medium hover:underline">
                    {repo.full_name}
                  </Link>
                  {repo.private && <Badge variant="outline">private</Badge>}
                  {!repo.enabled && <Badge variant="secondary">off</Badge>}
                </div>
                {isAdmin && (
                  <Button variant="outline" size="sm" onClick={() => toggle.mutate(repo)} disabled={toggle.isPending}>
                    {repo.enabled ? "Turn off reviews" : "Turn on reviews"}
                  </Button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
