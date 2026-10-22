import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ErrorNotice, Notice } from "@/components/notice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useSession } from "@/hooks/use-session"
import { apiPost, type AdminSettings } from "@/lib/api"

export function WebhooksCard({ webhooks }: { webhooks: AdminSettings["webhooks"] }) {
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const connect = useMutation({
    mutationFn: () => apiPost<{ url: string }>("/api/settings/webhooks"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  })
  const appSettings = session?.app ? `https://github.com/settings/apps/${session.app.slug}` : null

  return (
    <Card className="mt-6">
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-bold">Webhooks</h2>
          {webhooks.secret_set ? <Badge>connected</Badge> : <Badge variant="outline">off</Badge>}
        </div>
        <p className="text-sm text-muted-foreground">
          Webhooks let people ask for reviews from GitHub: mentioning the chakshu team, requesting it as a reviewer,
          and automatic reviews. Reviews started here in the portal don't need them.
        </p>
        <dl className="grid gap-1 text-sm">
          <dt className="text-muted-foreground">GitHub sends events to</dt>
          <dd>
            <code className="font-mono break-all">{webhooks.url}</code>
          </dd>
        </dl>
        {!webhooks.public && (
          <Notice>
            GitHub can't reach this address. Set <code className="font-mono">CHAKSHU_WEBHOOK_URL</code> to a public URL
            (your server, or a smee.io channel with{" "}
            <code className="font-mono">docker compose --profile smee up -d</code>), restart, then connect.
          </Notice>
        )}
        <ErrorNotice error={connect.error} />
        {connect.isSuccess && (
          <Notice>
            Done. On GitHub, open the app's settings
            {appSettings && (
              <>
                {" "}
                (<a className="underline" href={appSettings} target="_blank" rel="noreferrer">open</a>)
              </>
            )}
            , make sure <b>Webhook: Active</b> is ticked, and under <b>Permissions &amp; events</b> subscribe to{" "}
            {webhooks.events.join(", ")}.
          </Notice>
        )}
        <Button onClick={() => connect.mutate()} disabled={!webhooks.public || connect.isPending}>
          {webhooks.secret_set ? "Reconnect webhooks" : "Connect webhooks"}
        </Button>
      </CardContent>
    </Card>
  )
}
