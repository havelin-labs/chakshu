import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorNotice, Notice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPost, apiPut, type AppPermissions, type SecretsSync } from "@/lib/api"

const link = "text-brand-teal-ink hover:underline"

function PermissionGaps({ report }: { report: AppPermissions }) {
  if (report.ok) return <Notice>The GitHub App has every permission and event Chakshu needs.</Notice>
  return (
    <Notice tone="error">
      <div className="space-y-2">
        {(report.missing.length > 0 || report.missing_events.length > 0) && (
          <p>
            The app needs{" "}
            {[...report.missing, ...report.missing_events.map((e) => `the ${e} event`)].join(", ")}.{" "}
            <a className={link} href={report.settings_url} target="_blank" rel="noreferrer">
              Add them in the app's settings
            </a>
            .
          </p>
        )}
        {report.installations.map((gap) => (
          <p key={gap.account}>
            {gap.account} hasn't accepted {[...gap.missing, ...gap.missing_events].join(", ")}.{" "}
            <a className={link} href={gap.review_url} target="_blank" rel="noreferrer">
              Review the request
            </a>
            .
          </p>
        ))}
      </div>
    </Notice>
  )
}

// The runner labels every repo's workflow uses unless the repo sets its own.
function DefaultRunner({ current }: { current: string }) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (runs_on: string) => apiPut<{ actions_runs_on: string }>("/api/settings/actions/runner", { runs_on }),
    onSuccess: () => {
      setValue(null)
      queryClient.invalidateQueries({ queryKey: ["settings"] })
      queryClient.invalidateQueries({ queryKey: ["actions"] })
    },
  })
  const shown = value ?? current
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(shown)
      }}
    >
      <Label htmlFor="runs-on">Runner labels</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="runs-on"
          className="max-w-md font-mono"
          value={shown}
          placeholder="ubuntu-latest"
          onChange={(e) => setValue(e.target.value)}
          aria-describedby="runs-on-help"
        />
        <Button type="submit" variant="outline" disabled={save.isPending || value === null}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
      <p id="runs-on-help" className="text-xs text-muted-foreground">
        Where reviews run. Leave it as <code className="font-mono">ubuntu-latest</code> for GitHub-hosted runners, or
        use your own runners' labels, like <code className="font-mono">self-hosted, linux, x64</code>, so the code stays
        on your machines. Repositories can override it. After a change, each repository's workflow shows as out of date
        until you merge the update.
      </p>
      <ErrorNotice error={save.error} />
    </form>
  )
}

// Settings: what GitHub Actions needs from the app, and pushing the Claude credential to every repo.
export function ActionsCard({
  runnerUrl,
  runnerPublic,
  runsOn,
}: {
  runnerUrl: string
  runnerPublic: boolean
  runsOn: string
}) {
  const permissions = useQuery({
    queryKey: ["permissions"],
    queryFn: () => apiGet<AppPermissions>("/api/settings/permissions"),
  })
  const sync = useMutation({ mutationFn: () => apiPost<SecretsSync>("/api/settings/actions/secrets") })
  const failed = Object.entries(sync.data?.failed ?? {})

  return (
    <Card>
      <CardContent className="space-y-3">
        <h2 className="text-xl font-bold">GitHub Actions</h2>
        <p className="text-sm text-muted-foreground">
          Reviews run in each repository's Actions tab. Runners report back to{" "}
          <code className="font-mono">{runnerUrl}</code>, so GitHub has to be able to reach it. Chakshu copies the Claude
          credential into each repository's secrets when you save it here.
        </p>
        {!runnerPublic && (
          <Notice tone="error">
            Runners can't reach {runnerUrl} from GitHub, so reviews will start but never finish. On a laptop, start the
            tunnel with <code className="font-mono">docker compose --profile tunnel up -d</code>, set{" "}
            <code className="font-mono">CHAKSHU_RUNNER_URL</code> in .env to the trycloudflare.com address from{" "}
            <code className="font-mono">docker compose logs tunnel</code>, and restart web and worker.
          </Notice>
        )}
        <DefaultRunner current={runsOn} />
        <ErrorNotice error={permissions.error ?? sync.error} />
        {permissions.data && <PermissionGaps report={permissions.data} />}
        <Button variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}>
          {sync.isPending ? "Copying…" : "Copy the credential to all repositories"}
        </Button>
        {sync.data && (
          <Notice tone={failed.length ? "error" : undefined}>
            Updated {sync.data.synced.length} repositories.
            {failed.map(([repo, error]) => (
              <span key={repo} className="block">
                {repo}: {error}
              </span>
            ))}
          </Notice>
        )}
      </CardContent>
    </Card>
  )
}
