import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ErrorNotice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useSession } from "@/hooks/use-session"
import { apiGet, apiPost, type FailedEvent, type Health, type Ready } from "@/lib/api"
import { timeAgo } from "@/lib/format"

function StatusRow({ label, ok, detail }: { label: string; ok: boolean | undefined; detail?: string }) {
  return (
    <div className="flex items-center justify-between py-3">
      <span className="font-medium">{label}</span>
      <span className="flex items-center gap-3 text-sm text-muted-foreground">
        {detail}
        <StatusBadge status={ok === undefined ? "checking" : ok ? "ok" : "down"} />
      </span>
    </div>
  )
}

function FailedEvents() {
  const { data: session } = useSession()
  const queryClient = useQueryClient()
  const failed = useQuery({
    queryKey: ["failed-events"],
    queryFn: () => apiGet<FailedEvent[]>("/api/webhook-events/failed"),
  })
  const retry = useMutation({
    mutationFn: (id: string) => apiPost(`/api/webhook-events/${id}/retry`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["failed-events"] }),
  })

  return (
    <Card className="mt-6">
      <CardContent className="space-y-3">
        <h2 className="text-xl font-bold">Failed webhooks</h2>
        <ErrorNotice error={failed.error ?? retry.error} />
        {failed.data?.length === 0 && <p className="text-sm text-muted-foreground">None. Every event was handled.</p>}
        <div className="divide-y">
          {failed.data?.map((event) => (
            <div key={event.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium">
                  {event.event}
                  {event.action && ` · ${event.action}`}
                  {event.repo && <span className="text-muted-foreground"> in {event.repo}</span>}
                </p>
                <p className="text-xs break-all text-destructive">{event.error}</p>
                <p className="text-xs text-muted-foreground">
                  {timeAgo(event.received_at)} · {event.attempts} attempts
                </p>
              </div>
              {session?.user?.is_admin && (
                <Button variant="outline" size="sm" onClick={() => retry.mutate(event.id)} disabled={retry.isPending}>
                  Retry
                </Button>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function StatusPage() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: () => apiGet<Health>("/healthz") })
  const ready = useQuery({ queryKey: ["readyz"], queryFn: () => apiGet<Ready>("/readyz"), retry: false })

  return (
    <section className="max-w-2xl">
      <PageHeader eyebrow="Instance status" title="Service health">
        Whether the service and its database are running.
      </PageHeader>
      <Card>
        <CardContent className="divide-y">
          <StatusRow
            label="Service"
            ok={health.isPending ? undefined : health.isSuccess}
            detail={health.data && `v${health.data.version}`}
          />
          <StatusRow label="Database" ok={ready.isPending ? undefined : ready.isSuccess} />
        </CardContent>
      </Card>
      <FailedEvents />
    </section>
  )
}
