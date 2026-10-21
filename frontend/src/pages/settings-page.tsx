import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState, type FormEvent } from "react"

import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPut, type AdminSettings } from "@/lib/api"

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => apiGet<AdminSettings>("/api/settings") })
  const [form, setForm] = useState({ default_model: "", max_usd_per_review: "", reviewers_repo: "" })
  const [apiKey, setApiKey] = useState("")

  useEffect(() => {
    if (settings.data) {
      setForm({
        default_model: settings.data.default_model,
        max_usd_per_review: String(settings.data.max_usd_per_review),
        reviewers_repo: settings.data.reviewers_repo,
      })
    }
  }, [settings.data])

  const save = useMutation({
    mutationFn: () =>
      apiPut<AdminSettings>("/api/settings", {
        ...form,
        max_usd_per_review: Number(form.max_usd_per_review),
        anthropic_api_key: apiKey ? apiKey : null,
      }),
    onSuccess: (data) => {
      setApiKey("")
      queryClient.setQueryData(["settings"], data)
    },
  })
  const update = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }
  const key = settings.data?.anthropic_api_key

  return (
    <section className="max-w-2xl">
      <PageHeader eyebrow="Settings" title="Instance settings">
        Defaults for every reviewer. A reviewer's own reviewer.yaml wins where it sets a value.
      </PageHeader>
      <ErrorNotice error={settings.error} />
      <Card>
        <CardContent>
          <form onSubmit={submit} className="space-y-6">
            <Field
              id="api-key"
              label="Anthropic API key"
              hint={
                key?.set
                  ? `Saved (${key.hint}). Type a new key to replace it.`
                  : key?.from_env
                    ? "Using ANTHROPIC_API_KEY from the container environment."
                    : "Required before reviews can run. Stored encrypted."
              }
            >
              <Input
                id="api-key"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-ant-..."
              />
            </Field>
            <Field id="model" label="Default model" hint="Model alias (sonnet, opus, haiku) or a full model name.">
              <Input id="model" value={form.default_model} onChange={update("default_model")} className="max-w-xs" />
            </Field>
            <Field id="max-usd" label="Cost cap per review (USD)" hint="The review stops when it reaches this.">
              <Input
                id="max-usd"
                type="number"
                min="0.1"
                step="0.1"
                value={form.max_usd_per_review}
                onChange={update("max_usd_per_review")}
                className="max-w-32"
              />
            </Field>
            <Field
              id="repo"
              label="Reviewers repo name"
              hint="The repo in each organization that holds reviewer folders."
            >
              <Input id="repo" value={form.reviewers_repo} onChange={update("reviewers_repo")} className="max-w-xs" />
            </Field>
            <ErrorNotice error={save.error} />
            {save.isSuccess && <Notice>Saved.</Notice>}
            <Button type="submit" disabled={save.isPending || !settings.data}>
              Save settings
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  )
}
