import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"

import { ErrorNotice, Notice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPost, apiPut } from "@/lib/api"

type AlertSettings = { webhook: { set: boolean; hint: string }; thresholds: number[]; digest: boolean }
type Draft = { webhook: string; thresholds: string; digest: boolean }

const KEY = ["alert-settings"]

// Settings: warn admins before the monthly cap surprises them, and a weekly digest without names.
export function AlertsCard() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: KEY, queryFn: () => apiGet<AlertSettings>("/api/settings/alerts") })
  // Unsaved edits, on top of what the server has.
  const [draft, setDraft] = useState<Draft | null>(null)
  const form: Draft | null =
    draft ??
    (settings.data ? { webhook: "", thresholds: settings.data.thresholds.join(", "), digest: settings.data.digest } : null)

  const save = useMutation({
    mutationFn: (body: Draft) =>
      apiPut<AlertSettings>("/api/settings/alerts", {
        webhook: body.webhook.trim() || null,
        thresholds: body.thresholds
          .split(",")
          .map((part) => Number(part.trim()))
          .filter((n) => Number.isInteger(n) && n > 0),
        digest: body.digest,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(KEY, data)
      setDraft(null)
    },
  })
  const test = useMutation({ mutationFn: () => apiPost<{ ok: boolean }>("/api/settings/alerts/test") })

  if (!form) return null
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(form)
  }

  return (
    <Card>
      <CardContent className="space-y-3">
        <h2 className="text-xl font-bold">Spend alerts</h2>
        <p className="text-sm text-muted-foreground">
          Chakshu posts to Slack when this month's spend crosses each percentage of the monthly cap, once per month, and
          a digest every Monday with reviews, findings, spend and the noisiest skill. The digest never names people.
        </p>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="alerts-webhook">Slack incoming webhook</Label>
            <Input
              id="alerts-webhook"
              type="url"
              placeholder={settings.data?.webhook.set ? `Saved (${settings.data.webhook.hint}). Type a new one to replace it.` : "https://hooks.slack.com/services/..."}
              value={form.webhook}
              onChange={(e) => setDraft({ ...form, webhook: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="alerts-thresholds">Alert at (% of the monthly cap)</Label>
            <Input
              id="alerts-thresholds"
              value={form.thresholds}
              onChange={(e) => setDraft({ ...form, thresholds: e.target.value })}
            />
          </div>
          <label className="flex items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" checked={form.digest} onChange={(e) => setDraft({ ...form, digest: e.target.checked })} />
            Weekly digest on Mondays
          </label>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save alerts"}
            </Button>
            <Button type="button" variant="outline" disabled={!settings.data?.webhook.set || test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? "Sending…" : "Send a test message"}
            </Button>
          </div>
        </form>
        <ErrorNotice error={save.error ?? test.error ?? settings.error} />
        {test.isSuccess && <Notice>Test message sent. Check the Slack channel.</Notice>}
        <p className="text-xs text-muted-foreground">
          Alerts need a monthly cap, set above. Without a webhook nothing is sent.
        </p>
      </CardContent>
    </Card>
  )
}
