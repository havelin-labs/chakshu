import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ErrorNotice, Notice } from "@/components/notice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { apiGet, apiPost, type ActionsStatus } from "@/lib/api"

const WORKFLOW_TEXT: Record<ActionsStatus["workflow"], string> = {
  current: "The workflow is in place.",
  outdated: "The workflow is there but older than this Chakshu version expects.",
  missing: "The workflow isn't on the default branch yet.",
}

// Whether this repo can run reviews in GitHub Actions, and a button for admins to get it there.
export function RepoActionsCard({ repoId, isAdmin }: { repoId: string; isAdmin: boolean }) {
  const queryClient = useQueryClient()
  const status = useQuery({
    queryKey: ["actions", repoId],
    queryFn: () => apiGet<ActionsStatus>(`/api/repos/${repoId}/actions`),
  })
  const setUp = useMutation({
    mutationFn: () => apiPost<ActionsStatus>(`/api/repos/${repoId}/actions`),
    onSuccess: (data) => queryClient.setQueryData(["actions", repoId], data),
  })
  const data = status.data
  const hasSecret = data ? Object.values(data.secrets).some(Boolean) : false

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-bold">GitHub Actions</h2>
          {data && (data.ready ? <Badge>ready</Badge> : <Badge variant="outline">not set up</Badge>)}
        </div>
        <p className="text-sm text-muted-foreground">
          Reviews run in this repository's Actions tab. That needs the Chakshu workflow and the Claude credential as
          repository secrets.
        </p>
        <ErrorNotice error={status.error ?? setUp.error} />
        {data && (
          <ul className="space-y-1 text-sm">
            <li>{WORKFLOW_TEXT[data.workflow]}</li>
            <li>{hasSecret ? "The Claude credential is in the repository secrets." : "No Claude credential in the repository secrets."}</li>
          </ul>
        )}
        {data?.proposal_url && (
          <Notice>
            Merge{" "}
            <a className="text-brand-teal-ink hover:underline" href={data.proposal_url} target="_blank" rel="noreferrer">
              the workflow pull request
            </a>{" "}
            to finish.
          </Notice>
        )}
        {isAdmin && data && (data.workflow !== "current" || !hasSecret) && (
          <Button onClick={() => setUp.mutate()} disabled={setUp.isPending}>
            {setUp.isPending ? "Setting up…" : "Set up GitHub Actions"}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
