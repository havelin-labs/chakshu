import { useQuery } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet, type Health, type Ready } from "@/lib/api"

function StatusRow({ label, ok, detail }: { label: string; ok: boolean | undefined; detail?: string }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span>{label}</span>
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        {detail}
        <Badge variant={ok === undefined ? "outline" : ok ? "secondary" : "destructive"}>
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
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Instance status</CardTitle>
        <CardDescription>
          GitHub setup and sign-in come next. For now this page shows whether the service and its database are up.
        </CardDescription>
      </CardHeader>
      <CardContent className="divide-y">
        <StatusRow
          label="Service"
          ok={health.isPending ? undefined : health.isSuccess}
          detail={health.data && `v${health.data.version}`}
        />
        <StatusRow label="Database" ok={ready.isPending ? undefined : ready.isSuccess} />
      </CardContent>
    </Card>
  )
}
