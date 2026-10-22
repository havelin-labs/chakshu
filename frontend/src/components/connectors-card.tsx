import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"

import { ErrorNotice, Notice } from "@/components/notice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiDelete, apiGet, apiPost, apiPut, type ConnectorList } from "@/lib/api"

const KEY = ["connectors"]
const EMPTY = { name: "jira", kind: "jira", base_url: "", username: "", secret: "" }

function ConnectorForm({ kinds, onSaved }: { kinds: Record<string, string>; onSaved: () => void }) {
  const [form, setForm] = useState(EMPTY)
  const save = useMutation({
    mutationFn: () =>
      apiPut(`/api/connectors/${form.name}`, {
        kind: form.kind,
        base_url: form.base_url,
        username: form.username || null,
        secret: form.secret || null,
      }),
    onSuccess: () => {
      setForm(EMPTY)
      onSaved()
    },
  })
  const field = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }

  return (
    <form onSubmit={submit} className="grid gap-3 border-t pt-4 sm:grid-cols-2">
      <div className="space-y-1">
        <Label htmlFor="c-name">Name (used in reviewer.yaml)</Label>
        <Input id="c-name" value={form.name} onChange={field("name")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="c-kind">Kind</Label>
        <select
          id="c-kind"
          value={form.kind}
          onChange={field("kind")}
          className="h-8 w-full rounded-[4px] border bg-background px-2 text-sm"
        >
          {Object.entries(kinds).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1 sm:col-span-2">
        <Label htmlFor="c-url">Base URL</Label>
        <Input id="c-url" value={form.base_url} onChange={field("base_url")} placeholder="https://acme.atlassian.net" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="c-user">Account email</Label>
        <Input id="c-user" value={form.username} onChange={field("username")} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="c-secret">API token</Label>
        <Input id="c-secret" type="password" autoComplete="off" value={form.secret} onChange={field("secret")} />
      </div>
      <div className="space-y-2 sm:col-span-2">
        <ErrorNotice error={save.error} />
        <Button type="submit" disabled={!form.name || !form.base_url || save.isPending}>
          Save connector
        </Button>
      </div>
    </form>
  )
}

export function ConnectorsCard() {
  const queryClient = useQueryClient()
  const list = useQuery({ queryKey: KEY, queryFn: () => apiGet<ConnectorList>("/api/connectors") })
  const refresh = () => queryClient.invalidateQueries({ queryKey: KEY })
  const remove = useMutation({ mutationFn: (name: string) => apiDelete(`/api/connectors/${name}`), onSuccess: refresh })
  const check = useMutation({
    mutationFn: (name: string) => apiPost<{ ok: boolean; message: string }>(`/api/connectors/${name}/check`),
  })

  return (
    <Card className="mt-6">
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-xl font-bold">Connectors</h2>
          <p className="text-sm text-muted-foreground">
            Outside systems reviewers can read from. A reviewer uses one by listing its name under{" "}
            <code className="font-mono">connectors</code> in reviewer.yaml. Tokens are stored encrypted and never reach
            the review agent.
          </p>
        </div>
        <ErrorNotice error={list.error ?? remove.error ?? check.error} />
        {check.data && <Notice tone={check.data.ok ? "info" : "error"}>{check.data.message}</Notice>}
        <div className="divide-y">
          {list.data?.connectors.map((c) => (
            <div key={c.name} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <p className="font-medium">
                  {c.name} <Badge variant="outline">{list.data?.kinds[c.kind] ?? c.kind}</Badge>
                  {!c.enabled && <Badge variant="secondary">off</Badge>}
                </p>
                <p className="text-xs text-muted-foreground">
                  {c.base_url} · {c.username ?? "no user"} · token {c.secret_hint || "not set"}
                </p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => check.mutate(c.name)} disabled={check.isPending}>
                  Test
                </Button>
                <Button size="sm" variant="outline" onClick={() => remove.mutate(c.name)} disabled={remove.isPending}>
                  Remove
                </Button>
              </div>
            </div>
          ))}
        </div>
        {list.data && <ConnectorForm kinds={list.data.kinds} onSaved={refresh} />}
      </CardContent>
    </Card>
  )
}
