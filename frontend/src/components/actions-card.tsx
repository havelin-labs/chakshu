import { useMutation, useQuery } from "@tanstack/react-query"

import { ErrorNotice, Notice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { apiGet, apiPost, type AppPermissions, type SecretsSync } from "@/lib/api"

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

// Settings: what GitHub Actions needs from the app, and pushing the Claude credential to every repo.
export function ActionsCard({ runnerUrl, runnerPublic }: { runnerUrl: string; runnerPublic: boolean }) {
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
