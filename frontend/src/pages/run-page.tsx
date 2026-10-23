import { useQuery } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { useParams } from "react-router-dom"

import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { StatusBadge } from "@/components/status-badge"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { apiGet, isLive, type Finding, type RunDetail } from "@/lib/api"
import { cost, duration, shortSha, timeAgo } from "@/lib/format"

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">{label}</dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  )
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <div className="space-y-2 border-b py-4 last:border-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={finding.severity === "critical" || finding.severity === "high" ? "destructive" : "outline"}>
          {finding.severity}
        </Badge>
        <span className="font-semibold">{finding.title}</span>
      </div>
      <p className="font-mono text-xs text-muted-foreground">
        {finding.path}:{finding.line} · {finding.category}
        {finding.skill && ` · ${finding.skill}`}
      </p>
      <p className="text-sm whitespace-pre-wrap">{finding.body}</p>
      {finding.suggestion && (
        <pre className="overflow-x-auto rounded-[4px] border bg-background p-3 font-mono text-xs">{finding.suggestion}</pre>
      )}
    </div>
  )
}

export function RunPage() {
  const { id } = useParams()
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => apiGet<RunDetail>(`/api/runs/${id}`),
    refetchInterval: (query) => (query.state.data && isLive(query.state.data.status) ? 3_000 : false),
  })
  const data = run.data

  return (
    <section className="space-y-6">
      <ErrorNotice error={run.error} />
      {data && (
        <>
          <PageHeader
            eyebrow={`${data.repo} #${data.pr_number}`}
            title={data.pr_title ?? `Pull request #${data.pr_number}`}
            actions={
              <div className="flex gap-2">
                <a className={buttonVariants({ variant: "outline" })} href={data.pr_url} target="_blank" rel="noreferrer">
                  Pull request
                </a>
                {data.actions_run_url && (
                  <a className={buttonVariants({ variant: "outline" })} href={data.actions_run_url} target="_blank" rel="noreferrer">
                    Actions logs
                  </a>
                )}
                {data.review_url && (
                  <a className={buttonVariants()} href={data.review_url} target="_blank" rel="noreferrer">
                    {data.trigger === "reply" ? "Open answer" : "Open review"}
                  </a>
                )}
              </div>
            }
          />
          <Card>
            <CardContent>
              <dl className="grid grid-cols-2 gap-6 md:grid-cols-4">
                <Fact label="Status">
                  <StatusBadge status={data.status} /> {data.progress && <span className="ml-1">{data.progress}</span>}
                </Fact>
                <Fact label="Reviewer">
                  <span className="font-mono">{data.reviewer}</span>
                </Fact>
                <Fact label="Asked by">{data.requested_by ? `@${data.requested_by}` : data.trigger}</Fact>
                <Fact label="Commit">
                  <span className="font-mono">{shortSha(data.head_sha)}</span>
                </Fact>
                <Fact label="Model">{data.model ?? "—"}</Fact>
                <Fact label="Cost">{cost(data.cost_usd)}</Fact>
                <Fact label="Duration">{duration(data.duration_ms)}</Fact>
                <Fact label="Queued">{timeAgo(data.created_at)}</Fact>
              </dl>
            </CardContent>
          </Card>
          {data.note && <Notice>Note from the requester: {data.note}</Notice>}
          {data.error && <Notice tone="error">{data.error}</Notice>}
          {data.result && "reply" in data.result && (
            <Card>
              <CardContent>
                <h2 className="text-xl font-bold">Answer</h2>
                <p className="mt-2 text-sm whitespace-pre-wrap">{data.result.reply}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Finding {data.result.outcome === "open" || !data.result.outcome ? "left open" : `marked ${data.result.outcome}`}
                  {data.result.resolved && ". Resolved the thread"}
                </p>
              </CardContent>
            </Card>
          )}
          {data.result && "findings" in data.result && (
            <Card>
              <CardContent className="space-y-4">
                <div>
                  <h2 className="text-xl font-bold">Summary</h2>
                  <p className="mt-2 text-sm whitespace-pre-wrap">{data.result.summary}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {data.result.posted} posted inline, {data.result.summary_only} in the summary, {data.result.repeats}{" "}
                    already on the PR
                    {data.result.since && `. Reviewed only the changes since ${shortSha(data.result.since)}`}
                    {data.result.resolved ? `. Resolved ${data.result.resolved} outdated thread(s)` : null}
                  </p>
                </div>
                <div>
                  <h2 className="text-xl font-bold">Findings</h2>
                  {data.result.findings.length ? (
                    data.result.findings.map((finding, i) => <FindingCard key={i} finding={finding} />)
                  ) : (
                    <p className="mt-2 text-sm text-muted-foreground">No findings.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </section>
  )
}
