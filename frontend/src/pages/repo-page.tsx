import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useParams } from "react-router-dom"

import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { RepoActionsCard } from "@/components/repo-actions-card"
import { isActive, RunsTable } from "@/components/runs-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useSession } from "@/hooks/use-session"
import { apiGet, apiPost, type Pull, type Repo, type ReviewOutcome, type Run } from "@/lib/api"
import { timeAgo } from "@/lib/format"

function OutcomeNotice({ outcome }: { outcome: ReviewOutcome }) {
  if (outcome.refused) return <Notice tone="error">{outcome.refused.replace(/<!--.*?-->\s*/g, "")}</Notice>
  const parts = []
  if (outcome.queued.length) parts.push(`Queued ${outcome.queued.join(", ")}.`)
  if (outcome.already.length) parts.push(`Already reviewed at this commit: ${outcome.already.join(", ")}.`)
  return <Notice>{parts.join(" ") || "Nothing to run."}</Notice>
}

function PullRow({ repoId, pull }: { repoId: string; pull: Pull }) {
  const queryClient = useQueryClient()
  const [note, setNote] = useState("")
  const review = useMutation({
    mutationFn: () => apiPost<ReviewOutcome>(`/api/repos/${repoId}/pulls/${pull.number}/review`, { note: note || null }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs", repoId] }),
  })

  return (
    <div className="space-y-3 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <a href={pull.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
            #{pull.number} {pull.title}
          </a>
          <p className="text-xs text-muted-foreground">
            {pull.author && `@${pull.author} · `}updated {timeAgo(pull.updated_at)}
          </p>
        </div>
        {pull.draft && <Badge variant="outline">draft</Badge>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note, e.g. focus on the refund flow"
          className="max-w-md"
        />
        <Button onClick={() => review.mutate()} disabled={review.isPending}>
          {review.isPending ? "Requesting…" : "Review"}
        </Button>
      </div>
      <ErrorNotice error={review.error} />
      {review.data && <OutcomeNotice outcome={review.data} />}
    </div>
  )
}

export function RepoPage() {
  const { id = "" } = useParams()
  const repos = useQuery({ queryKey: ["repos"], queryFn: () => apiGet<Repo[]>("/api/repos") })
  const pulls = useQuery({ queryKey: ["pulls", id], queryFn: () => apiGet<Pull[]>(`/api/repos/${id}/pulls`) })
  const runs = useQuery({
    queryKey: ["runs", id],
    queryFn: () => apiGet<Run[]>(`/api/runs?repo_id=${id}&limit=20`),
    refetchInterval: (query) => (isActive(query.state.data) ? 5_000 : false),
  })
  const repo = repos.data?.find((r) => r.id === id)
  const { data: session } = useSession()

  return (
    <section className="space-y-6">
      <PageHeader eyebrow="Repository" title={repo?.full_name ?? "Repository"}>
        Ask for a review of any open pull request. Chakshu runs the reviewers that belong to your teams and fit the
        change.
      </PageHeader>
      {repo && !repo.enabled && <Notice>Reviews are turned off for this repository.</Notice>}
      <ErrorNotice error={pulls.error} />
      <RepoActionsCard repoId={id} isAdmin={Boolean(session?.user?.is_admin)} />
      <Card>
        <CardContent className="divide-y">
          <h2 className="pb-2 text-xl font-bold">Open pull requests</h2>
          {pulls.data?.length === 0 && <p className="py-4 text-sm text-muted-foreground">No open pull requests.</p>}
          {pulls.data?.map((pull) => <PullRow key={pull.number} repoId={id} pull={pull} />)}
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <h2 className="pb-2 text-xl font-bold">Recent reviews</h2>
          {runs.data && <RunsTable runs={runs.data} />}
        </CardContent>
      </Card>
    </section>
  )
}
