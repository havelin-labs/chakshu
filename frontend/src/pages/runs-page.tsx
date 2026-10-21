import { useQuery } from "@tanstack/react-query"

import { ErrorNotice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { isActive, RunsTable } from "@/components/runs-table"
import { Card, CardContent } from "@/components/ui/card"
import { apiGet, type Run } from "@/lib/api"

export function RunsPage() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiGet<Run[]>("/api/runs"),
    // Poll while something is queued or running, so progress shows without a reload.
    refetchInterval: (query) => (isActive(query.state.data) ? 5_000 : false),
  })

  return (
    <section>
      <PageHeader eyebrow="Reviews" title="Recent reviews">
        Every review Chakshu has run, newest first. Ask for one by commenting your org's chakshu handle on a pull
        request, or from Repositories.
      </PageHeader>
      <ErrorNotice error={runs.error} />
      <Card>
        <CardContent>{runs.data && <RunsTable runs={runs.data} />}</CardContent>
      </Card>
    </section>
  )
}
