import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorNotice, Notice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPatch, apiPost, type AnalyticsPrivacy, type AuditRow } from "@/lib/api"
import { timeAgo } from "@/lib/format"

const ACTION_LABEL: Record<string, string> = {
  "people.directory.view": "viewed the People directory",
  "people.detail.view": "viewed a person's page",
  "people.activity.view": "viewed a person's activity",
  "people.export": "exported people as CSV",
  "settings.analytics.update": "changed the privacy settings",
  "settings.analytics.works_council": "turned on works council mode",
}

function AuditLog() {
  const [open, setOpen] = useState(false)
  const log = useQuery({
    queryKey: ["analytics-audit"],
    queryFn: () => apiGet<AuditRow[]>("/api/settings/analytics/audit?limit=100"),
    enabled: open,
  })
  return (
    <div className="space-y-2 border-t pt-3">
      <Button size="sm" variant="outline" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide the audit log" : "Show the audit log"}
      </Button>
      {open && (
        <>
          <ErrorNotice error={log.error} />
          {log.data?.length === 0 && <p className="text-sm text-muted-foreground">Nothing logged yet.</p>}
          {!!log.data?.length && (
            <ul className="max-h-72 divide-y overflow-auto rounded-[4px] border text-sm">
              {log.data.map((row, i) => (
                <li key={`${row.at}-${i}`} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                  <span>
                    <span className="font-medium">@{row.user}</span> {ACTION_LABEL[row.action] ?? row.action}
                    {row.target && <span className="text-muted-foreground"> (@{row.target})</span>}
                  </span>
                  <span className="text-muted-foreground" title={row.at}>
                    {timeAgo(row.at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

// Whether analytics name people, the smallest group shown, how long people stay on reviews, and
// whether named people can be exported. Every change is audited by the server.
export function AnalyticsPrivacyCard() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ["analytics-privacy"], queryFn: () => apiGet<AnalyticsPrivacy>("/api/settings/analytics") })
  // Unsaved edits, on top of what the server has.
  const [draft, setForm] = useState<AnalyticsPrivacy | null>(null)
  const form = draft ?? settings.data
  const refresh = () => {
    setForm(null)
    queryClient.invalidateQueries({ queryKey: ["analytics-privacy"] })
    queryClient.invalidateQueries({ queryKey: ["analytics"] })
    queryClient.invalidateQueries({ queryKey: ["analytics-audit"] })
  }
  const save = useMutation({
    mutationFn: (body: AnalyticsPrivacy) =>
      apiPatch<AnalyticsPrivacy>("/api/settings/analytics", { ...body, retention_days: body.retention_days ?? 0 }),
    onSuccess: refresh,
  })
  const worksCouncil = useMutation({
    mutationFn: () => apiPost<AnalyticsPrivacy>("/api/settings/analytics/works-council"),
    onSuccess: refresh,
  })
  if (!form) return null
  return (
    <Card id="privacy" className="scroll-mt-24">
      <CardContent className="space-y-4">
        <h3 className="font-semibold">Privacy</h3>
        <div className="flex flex-wrap items-end gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.show_names} onChange={(e) => setForm({ ...form, show_names: e.target.checked })} />
            Show people by name
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.export_people}
              onChange={(e) => setForm({ ...form, export_people: e.target.checked })}
            />
            Allow CSV export of named people
          </label>
          <div className="space-y-1">
            <Label htmlFor="min-group">Smallest group shown</Label>
            <Input
              id="min-group"
              type="number"
              min={1}
              max={100}
              className="w-24"
              value={form.min_group}
              onChange={(e) => setForm({ ...form, min_group: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="retention">Keep people on reviews for (days)</Label>
            <Input
              id="retention"
              type="number"
              min={0}
              max={3650}
              className="w-32"
              placeholder="Always"
              value={form.retention_days ?? ""}
              onChange={(e) => setForm({ ...form, retention_days: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </div>
          <Button size="sm" onClick={() => save.mutate(form)} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        <ErrorNotice error={save.error ?? worksCouncil.error} />
        <p className="text-xs text-muted-foreground">
          Slices covering fewer people than the smallest group size are hidden, so a filter can't single someone out; 1
          turns this off, otherwise use 3 to 100. With a retention period, Chakshu clears who asked for and who authored
          reviews older than that once a day; repository, reviewer and cost numbers stay. Leave it empty to keep them.
        </p>
        <Notice>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Works council or employee agreement pending? One step turns names off, raises the smallest group to 10 and
              blocks exporting named people.
            </span>
            <Button size="sm" variant="outline" onClick={() => worksCouncil.mutate()} disabled={worksCouncil.isPending}>
              {worksCouncil.isPending ? "Applying…" : "Turn on works council mode"}
            </Button>
          </div>
        </Notice>
        <AuditLog />
      </CardContent>
    </Card>
  )
}
