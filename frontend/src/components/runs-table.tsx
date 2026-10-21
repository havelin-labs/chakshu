import { Link } from "react-router-dom"

import { StatusBadge } from "@/components/status-badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Run } from "@/lib/api"
import { cost, duration, timeAgo } from "@/lib/format"

export function RunsTable({ runs }: { runs: Run[] }) {
  if (!runs.length) {
    return <p className="py-6 text-sm text-muted-foreground">No reviews yet.</p>
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Pull request</TableHead>
          <TableHead>Reviewer</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="hidden md:table-cell">Asked by</TableHead>
          <TableHead className="hidden text-right md:table-cell">Cost</TableHead>
          <TableHead className="hidden text-right md:table-cell">Time</TableHead>
          <TableHead className="text-right">When</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id}>
            <TableCell className="max-w-72">
              <Link to={`/runs/${run.id}`} className="block truncate font-medium hover:underline">
                {run.pr_title ?? `#${run.pr_number}`}
              </Link>
              <span className="text-xs text-muted-foreground">
                {run.repo}#{run.pr_number}
              </span>
            </TableCell>
            <TableCell className="font-mono text-xs">{run.reviewer}</TableCell>
            <TableCell>
              <StatusBadge status={run.status} />
            </TableCell>
            <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
              {run.requested_by ?? run.trigger}
            </TableCell>
            <TableCell className="hidden text-right font-mono text-xs md:table-cell">{cost(run.cost_usd)}</TableCell>
            <TableCell className="hidden text-right font-mono text-xs md:table-cell">
              {duration(run.duration_ms)}
            </TableCell>
            <TableCell className="text-right text-sm text-muted-foreground">{timeAgo(run.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export const isActive = (runs: Run[] | undefined) =>
  Boolean(runs?.some((r) => r.status === "queued" || r.status === "running"))
