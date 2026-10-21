import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useSession } from "@/hooks/use-session"
import { apiGet, apiPost, type Reviewer } from "@/lib/api"

type SyncResult = { account: string; repo: string; found: boolean; reviewers: number; broken: number }

function Chips({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm">
      <span className="w-16 text-muted-foreground">{label}</span>
      {items.map((item) => (
        <code key={item} className="rounded-[4px] border bg-background px-1.5 py-0.5 font-mono text-xs">
          {item}
        </code>
      ))}
    </div>
  )
}

function ReviewerCard({ reviewer }: { reviewer: Reviewer }) {
  return (
    <Card>
      <CardContent className="space-y-3 py-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-lg font-semibold">{reviewer.name}</h3>
            <p className="text-sm text-muted-foreground">
              {[reviewer.product, `@${reviewer.account}/${reviewer.owner_team}`].filter(Boolean).join(" · ")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {reviewer.model && <Badge variant="outline">{reviewer.model}</Badge>}
            {reviewer.errors.length > 0 ? <Badge variant="destructive">broken</Badge> : <Badge>ready</Badge>}
          </div>
        </div>
        {reviewer.description && <p className="text-sm">{reviewer.description}</p>}
        <Chips label="Repos" items={reviewer.repos} />
        <Chips label="Paths" items={reviewer.paths} />
        <Chips label="Skills" items={reviewer.skills} />
        <Chips label="Auto" items={reviewer.auto} />
        {reviewer.errors.length > 0 && (
          <Notice tone="error">
            <ul className="list-disc space-y-1 pl-4">
              {reviewer.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </Notice>
        )}
        {reviewer.source_url && (
          <a className="text-sm text-brand-teal-ink hover:underline" href={reviewer.source_url} target="_blank" rel="noreferrer">
            View on GitHub at {reviewer.source_sha.slice(0, 7)}
          </a>
        )}
      </CardContent>
    </Card>
  )
}

export function ReviewersPage() {
  const { data: session } = useSession()
  const queryClient = useQueryClient()
  const reviewers = useQuery({ queryKey: ["reviewers"], queryFn: () => apiGet<Reviewer[]>("/api/reviewers") })
  const sync = useMutation({
    mutationFn: () => apiPost<SyncResult[]>("/api/reviewers/sync"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reviewers"] }),
  })
  const missing = sync.data?.filter((r) => !r.found) ?? []

  return (
    <section>
      <PageHeader
        eyebrow="Reviewers"
        title="Your teams' reviewers"
        actions={
          session?.user?.is_admin && (
            <Button variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}>
              {sync.isPending ? "Syncing…" : "Sync from GitHub"}
            </Button>
          )
        }
      >
        Each one is a folder in your organization's reviewers repo. Edit them there with a pull request; Chakshu picks
        up changes when they merge.
      </PageHeader>
      <div className="space-y-4">
        <ErrorNotice error={reviewers.error ?? sync.error} />
        {missing.map((r) => (
          <Notice key={r.repo}>
            No <code className="font-mono">{r.repo}</code> repo found, or the app can't see it. Create it from the
            template and give the Chakshu app access.
          </Notice>
        ))}
        {reviewers.data?.length === 0 && (
          <Notice>No reviewers yet. Add a folder under reviewers/ in your reviewers repo, then sync.</Notice>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {reviewers.data?.map((reviewer) => <ReviewerCard key={reviewer.id} reviewer={reviewer} />)}
        </div>
      </div>
    </section>
  )
}
