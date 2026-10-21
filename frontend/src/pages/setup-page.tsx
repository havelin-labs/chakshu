import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"
import { Navigate } from "react-router-dom"

import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { SESSION_KEY, useSession } from "@/hooks/use-session"
import { apiPost } from "@/lib/api"

type ManifestResponse = { action: string; manifest: object; webhooks: boolean }

// GitHub's manifest flow needs a real form POST to github.com, not a fetch.
function postToGitHub({ action, manifest }: ManifestResponse) {
  const form = document.createElement("form")
  form.method = "post"
  form.action = action
  const input = document.createElement("input")
  input.type = "hidden"
  input.name = "manifest"
  input.value = JSON.stringify(manifest)
  form.appendChild(input)
  document.body.appendChild(form)
  form.submit()
}

function ClaimStep() {
  const queryClient = useQueryClient()
  const [code, setCode] = useState("")
  const claim = useMutation({
    mutationFn: () => apiPost("/api/setup/claim", { code }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SESSION_KEY }),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    claim.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="code">Setup code</Label>
        <Input
          id="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="ABCD-EFGH"
          autoComplete="off"
          className="max-w-xs font-mono uppercase"
        />
        <p className="text-sm text-muted-foreground">
          Find it with <code className="font-mono">docker compose logs web | grep "Setup code"</code>
        </p>
      </div>
      <ErrorNotice error={claim.error} />
      <Button type="submit" disabled={!code || claim.isPending}>
        Continue
      </Button>
    </form>
  )
}

function CreateAppStep({ webhooks }: { webhooks: boolean }) {
  const [org, setOrg] = useState("")
  const [name, setName] = useState("")
  const suggested = org ? `chakshu-${org}` : "chakshu"
  const create = useMutation({
    mutationFn: () => apiPost<ManifestResponse>("/api/setup/manifest", { org, name: name || suggested }),
    onSuccess: postToGitHub,
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="space-y-2">
        <Label htmlFor="org">GitHub organization</Label>
        <Input id="org" value={org} onChange={(e) => setOrg(e.target.value)} placeholder="acme" className="max-w-sm" />
        <p className="text-sm text-muted-foreground">Leave empty to create the app under your personal account.</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="name">App name</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={suggested}
          className="max-w-sm"
        />
        <p className="text-sm text-muted-foreground">App names are unique across GitHub.</p>
      </div>
      {!webhooks && (
        <Notice>
          This instance isn't reachable from the internet, so the app is created without webhooks. Reviews started from
          the portal still work. Set <code className="font-mono">CHAKSHU_WEBHOOK_URL</code> to a public URL (a smee.io
          channel works) before this step to get mentions and automatic reviews.
        </Notice>
      )}
      <ErrorNotice error={create.error} />
      <Button type="submit" disabled={create.isPending}>
        Create on GitHub
      </Button>
    </form>
  )
}

export function SetupPage() {
  const { data: session } = useSession()
  if (!session) return null
  if (session.configured) return <Navigate to="/" replace />

  return (
    <section className="max-w-2xl">
      <PageHeader eyebrow={session.setup_claimed ? "Step 2 of 3" : "Step 1 of 3"} title="Connect Chakshu to GitHub">
        {session.setup_claimed
          ? "Chakshu creates a GitHub App that belongs to this install. GitHub hands the keys straight back, so you never copy a private key."
          : "First, prove you run this server. The setup code is printed in the web container's logs."}
      </PageHeader>
      <Card>
        <CardContent className="py-2">
          {session.setup_claimed ? <CreateAppStep webhooks={session.webhooks} /> : <ClaimStep />}
        </CardContent>
      </Card>
    </section>
  )
}
