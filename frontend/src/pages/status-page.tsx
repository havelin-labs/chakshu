import { useQuery } from "@tanstack/react-query"

import { Eyebrow } from "@/components/eyebrow"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { apiGet, type Health, type Ready } from "@/lib/api"

function StatusRow({ label, ok, detail }: { label: string; ok: boolean | undefined; detail?: string }) {
  return (
    <div className="flex items-center justify-between py-3">
      <span className="font-medium">{label}</span>
      <span className="flex items-center gap-3 text-sm text-muted-foreground">
        {detail}
        <Badge variant={ok === undefined ? "outline" : ok ? "default" : "destructive"}>
          {ok === undefined ? "checking" : ok ? "ok" : "down"}
        </Badge>
      </span>
    </div>
  )
}

export function StatusPage() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: () => apiGet<Health>("/healthz") })
  const ready = useQuery({ queryKey: ["readyz"], queryFn: () => apiGet<Ready>("/readyz"), retry: false })

  return (
    <section className="max-w-2xl space-y-8">
      <div className="space-y-4">
        <Eyebrow>Instance status</Eyebrow>
        <h1 className="text-4xl font-bold tracking-tight">Your reviewer is up.</h1>
        <p className="text-muted-foreground">
          GitHub setup and sign-in come next. For now this page shows whether the service and its database are
          running.
        </p>
      </div>
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
