import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorNotice, Notice } from "@/components/notice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPost, apiPut, type ActionsStatus } from "@/lib/api"

const WORKFLOW_TEXT: Record<ActionsStatus["workflow"], string> = {
  current: "The workflow is in place.",
  outdated: "The workflow is there but doesn't match the current settings (Chakshu version or runner labels).",
  missing: "The workflow isn't on the default branch yet.",
}

// This repo's own runner labels. Empty means the org default from Settings.
function RepoRunner({ repoId, status }: { repoId: string; status: ActionsStatus }) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (runs_on: string) => apiPut(`/api/repos/${repoId}`, { runs_on }),
    onSuccess: () => {
      setValue(null)
      queryClient.invalidateQueries({ queryKey: ["actions", repoId] })
    },
  })
  const shown = value ?? status.runs_on_override ?? ""
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(shown)
      }}
    >
      <Label htmlFor={`runs-on-${repoId}`}>Runner labels for this repository</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id={`runs-on-${repoId}`}
          className="max-w-md font-mono"
          value={shown}
          placeholder={`Org default: ${status.runs_on.join(", ")}`}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button type="submit" variant="outline" disabled={save.isPending || value === null}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
      <ErrorNotice error={save.error} />
    </form>
  )
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
            <li>
              Runs on <code className="font-mono">{data.runs_on.join(", ")}</code>
              {data.runs_on.includes("self-hosted") ? " (your own runners)." : " (GitHub-hosted)."}
            </li>
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
        {isAdmin && data && <RepoRunner repoId={repoId} status={data} />}
        {isAdmin && data && (data.workflow !== "current" || !hasSecret) && (
          <Button onClick={() => setUp.mutate()} disabled={setUp.isPending}>
            {setUp.isPending ? "Setting up…" : "Set up GitHub Actions"}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
