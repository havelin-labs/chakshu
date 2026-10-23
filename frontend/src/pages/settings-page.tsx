import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState, type FormEvent } from "react"

import { ActionsCard } from "@/components/actions-card"
import { ConnectorsCard } from "@/components/connectors-card"
import { WebhooksCard } from "@/components/webhooks-card"
import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiPut, type AdminSettings } from "@/lib/api"
import { cost } from "@/lib/format"

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
    </div>
  )
}

const ACCESS_LABEL: Record<AdminSettings["access"], string> = {
  api_key: "API key",
  subscription: "subscription token",
  environment: "container environment",
  none: "nothing set yet",
}

type SecretStatus = { set: boolean; hint: string; from_env: boolean }

function SecretField(props: {
  id: string
  label: string
  placeholder: string
  envName: string
  emptyHint: string
  status: SecretStatus | undefined
  value: string
  onChange: (value: string) => void
}) {
  const { status } = props
  const hint = status?.set
    ? `Saved (${status.hint}). Type a new one to replace it.`
    : status?.from_env
      ? `Using ${props.envName} from the container environment.`
      : `${props.emptyHint} Stored encrypted.`
  return (
    <Field id={props.id} label={props.label} hint={hint}>
      <Input
        id={props.id}
        type="password"
        autoComplete="off"
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
      />
    </Field>
  )
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => apiGet<AdminSettings>("/api/settings") })
  const [form, setForm] = useState({
    default_model: "",
    max_usd_per_review: "",
    monthly_cap_usd: "",
    reviewers_repo: "",
  })
  const [secrets, setSecrets] = useState({ anthropic_api_key: "", claude_oauth_token: "" })

  useEffect(() => {
    if (settings.data) {
      setForm({
        default_model: settings.data.default_model,
        max_usd_per_review: String(settings.data.max_usd_per_review),
        monthly_cap_usd: settings.data.monthly_cap_usd == null ? "" : String(settings.data.monthly_cap_usd),
        reviewers_repo: settings.data.reviewers_repo,
      })
    }
  }, [settings.data])

  const save = useMutation({
    mutationFn: () =>
      apiPut<AdminSettings>("/api/settings", {
        ...form,
        max_usd_per_review: Number(form.max_usd_per_review),
        monthly_cap_usd: form.monthly_cap_usd ? Number(form.monthly_cap_usd) : null,
        // Only send secrets that were typed; empty means "keep what's saved".
        anthropic_api_key: secrets.anthropic_api_key || null,
        claude_oauth_token: secrets.claude_oauth_token || null,
      }),
    onSuccess: (data) => {
      setSecrets({ anthropic_api_key: "", claude_oauth_token: "" })
      queryClient.setQueryData(["settings"], data)
    },
  })
  const update = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate()
  }
  const secretField = (name: keyof typeof secrets) => ({
    status: settings.data?.[name],
    value: secrets[name],
    onChange: (value: string) => setSecrets({ ...secrets, [name]: value }),
  })

  return (
    <section className="max-w-2xl">
      <PageHeader eyebrow="Settings" title="Instance settings">
        Defaults for every reviewer. A reviewer's own reviewer.yaml wins where it sets a value.
      </PageHeader>
      <ErrorNotice error={settings.error} />
      <Card>
        <CardContent>
          <form onSubmit={submit} className="space-y-6">
            <div className="space-y-4 rounded-[4px] border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold">Claude access</h2>
                <span className="text-xs text-muted-foreground">Reviews use: {ACCESS_LABEL[settings.data?.access ?? "none"]}</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Set one. If both are set, the API key is used.
              </p>
              <SecretField
                id="api-key"
                label="Anthropic API key"
                placeholder="sk-ant-api..."
                envName="ANTHROPIC_API_KEY"
                emptyHint="From console.anthropic.com. Paid from your Console credits."
                {...secretField("anthropic_api_key")}
              />
              <SecretField
                id="oauth-token"
                label="Claude subscription token"
                placeholder="sk-ant-oat..."
                envName="CLAUDE_CODE_OAUTH_TOKEN"
                emptyHint="Run claude setup-token with a Pro or Max account and paste the token. Reviews then count against that person's subscription limits."
                {...secretField("claude_oauth_token")}
              />
              <Notice>
                Anthropic's terms restrict using claude.ai subscriptions in third-party products. Check that your use is
                allowed before relying on a subscription token, and prefer an API key for shared or production use.
              </Notice>
            </div>
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
              id="monthly-cap"
              label="Monthly spend cap (USD)"
              hint={`Spent this month: ${cost(settings.data?.spend_this_month ?? null)}. New reviews are refused once this is reached. Leave empty for no cap.`}
            >
              <Input
                id="monthly-cap"
                type="number"
                min="1"
                step="1"
                value={form.monthly_cap_usd}
                onChange={update("monthly_cap_usd")}
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
      {settings.data && <WebhooksCard webhooks={settings.data.webhooks} />}
      {settings.data && <ActionsCard runnerUrl={settings.data.runner_url} runnerPublic={settings.data.runner_public} />}
      <ConnectorsCard />
    </section>
  )
}
