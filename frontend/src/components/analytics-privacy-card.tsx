import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorNotice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPatch, type AnalyticsPrivacy } from "@/lib/api"

// Whether analytics name people, and the smallest group shown. Changes are audited by the server.
export function AnalyticsPrivacyCard() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ["analytics-privacy"], queryFn: () => apiGet<AnalyticsPrivacy>("/api/settings/analytics") })
  // Unsaved edits, on top of what the server has.
  const [draft, setForm] = useState<AnalyticsPrivacy | null>(null)
  const form = draft ?? settings.data
  const save = useMutation({
    mutationFn: (body: AnalyticsPrivacy) => apiPatch<AnalyticsPrivacy>("/api/settings/analytics", body),
    onSuccess: () => {
      setForm(null)
      queryClient.invalidateQueries({ queryKey: ["analytics-privacy"] })
      queryClient.invalidateQueries({ queryKey: ["analytics"] })
    },
  })
  if (!form) return null
  return (
    <Card id="privacy" className="scroll-mt-24">
      <CardContent className="space-y-3">
        <h3 className="font-semibold">Privacy</h3>
        <div className="flex flex-wrap items-end gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.show_names} onChange={(e) => setForm({ ...form, show_names: e.target.checked })} />
            Show people by name
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
          <Button size="sm" onClick={() => save.mutate(form)} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        <ErrorNotice error={save.error} />
        <p className="text-xs text-muted-foreground">
          Turn names off where a works council or employee agreement asks for it. Slices covering fewer people than the
          smallest group size are hidden, so a filter can't single someone out; 1 turns this off, otherwise use 3 to
          100. Every view and export of named people is logged.
        </p>
      </CardContent>
    </Card>
  )
}

