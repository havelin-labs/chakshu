import { useQuery } from "@tanstack/react-query"

import { PageHeader } from "@/components/page-header"
import { StatusBadge } from "@/components/status-badge"
import { Card, CardContent } from "@/components/ui/card"
import { apiGet, type Health, type Ready } from "@/lib/api"

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
    </section>
  )
}
