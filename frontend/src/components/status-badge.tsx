import { Badge } from "@/components/ui/badge"

// Every status word the portal shows, mapped to one look. Runs reuse this later.
const VARIANTS: Record<string, "default" | "outline" | "secondary" | "destructive"> = {
  ok: "default",
  succeeded: "default",
  running: "secondary",
  queued: "outline",
  checking: "outline",
  cancelled: "outline",
  down: "destructive",
  failed: "destructive",
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={VARIANTS[status] ?? "outline"}>{status}</Badge>
}
