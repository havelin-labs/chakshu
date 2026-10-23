import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent, type ReactNode } from "react"
import { Link, useParams } from "react-router-dom"

import { Field } from "@/components/field"
import { ErrorNotice, Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  apiGet,
  apiPost,
  SEVERITIES,
  type ReviewerDraft,
  type ReviewerOptions,
  type ReviewerProposal,
  type Severity,
  type SkillDraft,
} from "@/lib/api"

const selectClass = "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring"
const link = "text-brand-teal-ink hover:underline"

const blank = (account: string): ReviewerDraft => ({
  account,
  name: "",
  product: null,
  description: null,
  owner_team: "",
  model: null,
  repos: ["*"],
  paths: [],
  auto: [],
  connectors: [],
  limits: {},
  fail_check_on: null,
  tools: [],
  rules: "",
  skills: [],
  shared_skills: [],
})

const lines = (items: string[]) => items.join("\n")
const toLines = (text: string) => text.split("\n")
const numberOrUndefined = (text: string) => (text.trim() === "" ? undefined : Number(text))

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-4 rounded-[4px] border p-4">
      <div className="space-y-1">
        <h2 className="text-base font-semibold">{title}</h2>
        {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

function Checkboxes({
  options,
  checked,
  onChange,
}: {
  options: string[]
  checked: string[]
  onChange: (checked: string[]) => void
}) {
  return (
    <div className="flex flex-wrap gap-4">
      {options.map((option) => (
        <label key={option} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="accent-brand-teal"
            checked={checked.includes(option)}
            onChange={(e) => onChange(e.target.checked ? [...checked, option] : checked.filter((c) => c !== option))}
          />
          <code className="font-mono text-xs">{option}</code>
        </label>
      ))}
    </div>
  )
}

function SkillEditor({
  index,
  skill,
  onChange,
  onRemove,
}: {
  index: number
  skill: SkillDraft
  onChange: (skill: SkillDraft) => void
  onRemove: () => void
}) {
  return (
    <div className="space-y-3 rounded-[4px] border bg-background p-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1">
          <Field id={`skill-${index}-name`} label="Skill name">
            <Input
              id={`skill-${index}-name`}
              value={skill.name}
              onChange={(e) => onChange({ ...skill, name: e.target.value })}
              placeholder="refund-safety"
            />
          </Field>
        </div>
        <Button type="button" variant="outline" onClick={onRemove}>
          Remove
        </Button>
      </div>
      <Field
        id={`skill-${index}-description`}
        label="Description"
        hint="What the skill checks and when it applies. Claude reads this to decide when to use it."
      >
        <Textarea
          id={`skill-${index}-description`}
          value={skill.description}
          onChange={(e) => onChange({ ...skill, description: e.target.value })}
        />
      </Field>
      <Field id={`skill-${index}-body`} label="Instructions" hint="The body of SKILL.md, in Markdown.">
        <Textarea
          id={`skill-${index}-body`}
          value={skill.body}
          onChange={(e) => onChange({ ...skill, body: e.target.value })}
          className="min-h-40 font-mono"
        />
      </Field>
    </div>
  )
}

function ReviewerForm({
  initial,
  reviewerId,
  options,
}: {
  initial: ReviewerDraft
  reviewerId?: string
  options: ReviewerOptions
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState(initial)
  const [maxUsd, setMaxUsd] = useState(initial.limits.max_usd == null ? "" : String(initial.limits.max_usd))
  const [maxFindings, setMaxFindings] = useState(String(initial.limits.max_findings ?? 10))
  const set = <K extends keyof ReviewerDraft>(key: K, value: ReviewerDraft[K]) => setDraft({ ...draft, [key]: value })
  const setSkill = (index: number, skill: SkillDraft) =>
    set(
      "skills",
      draft.skills.map((s, i) => (i === index ? skill : s)),
    )

  const propose = useMutation({
    mutationFn: () =>
      apiPost<ReviewerProposal>("/api/reviewers/proposals", {
        reviewer_id: reviewerId ?? null,
        draft: {
          ...draft,
          limits: {
            ...draft.limits,
            max_usd: numberOrUndefined(maxUsd) ?? null,
            max_findings: numberOrUndefined(maxFindings) ?? 10,
          },
        },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reviewers"] }),
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    propose.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <Section title="Reviewer">
        {!reviewerId && options.accounts.length > 1 && (
          <Field id="account" label="Organization">
            <select
              id="account"
              className={selectClass}
              value={draft.account}
              onChange={(e) => set("account", e.target.value)}
            >
              {options.accounts.map((account) => (
                <option key={account}>{account}</option>
              ))}
            </select>
          </Field>
        )}
        <Field
          id="name"
          label="Name"
          hint="Lowercase letters, digits and dashes. People call it with @org/chakshu followed by this name."
        >
          <Input id="name" value={draft.name} onChange={(e) => set("name", e.target.value)} className="max-w-xs" />
        </Field>
        <Field id="product" label="Product" hint="Optional. What the reviewer looks after, shown in the portal.">
          <Input
            id="product"
            value={draft.product ?? ""}
            onChange={(e) => set("product", e.target.value)}
            className="max-w-md"
          />
        </Field>
        <Field id="description" label="Description">
          <Textarea id="description" value={draft.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field id="owner-team" label="Owner team" hint="The GitHub team that looks after this reviewer. Shown for information.">
          <Input
            id="owner-team"
            value={draft.owner_team}
            onChange={(e) => set("owner_team", e.target.value)}
            className="max-w-xs"
          />
        </Field>
        <Field
          id="model"
          label="Model"
          hint={`Leave empty to use the default${options.default_model ? ` (${options.default_model})` : ""}.`}
        >
          <Input
            id="model"
            list="models"
            value={draft.model ?? ""}
            onChange={(e) => set("model", e.target.value)}
            className="max-w-xs"
          />
          <datalist id="models">
            {options.models.map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
        </Field>
      </Section>

      <Section title="What it reviews" hint="Without a name in the request, a reviewer runs when it covers the repository and files.">
        <Field id="repos" label="Repositories" hint="One glob per line, such as payments-* or acme/web. * covers every repository.">
          <Textarea
            id="repos"
            value={lines(draft.repos)}
            onChange={(e) => set("repos", toLines(e.target.value))}
            className="font-mono"
          />
        </Field>
        <Field id="paths" label="Paths" hint="One gitignore-style pattern per line. Empty covers every file.">
          <Textarea
            id="paths"
            value={lines(draft.paths)}
            onChange={(e) => set("paths", toLines(e.target.value))}
            className="font-mono"
          />
        </Field>
        <div className="space-y-2">
          <p className="text-sm font-medium">Run on its own when a pull request is</p>
          <Checkboxes options={options.auto_events} checked={draft.auto} onChange={(auto) => set("auto", auto)} />
        </div>
        {options.connectors.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Connectors</p>
            <Checkboxes
              options={options.connectors}
              checked={draft.connectors}
              onChange={(connectors) => set("connectors", connectors)}
            />
          </div>
        )}
      </Section>

      <Section title="Limits">
        <div className="flex flex-wrap gap-6">
          <Field id="max-usd" label="Cost cap (USD)" hint="Empty uses the instance setting.">
            <Input
              id="max-usd"
              type="number"
              min="0.1"
              step="0.1"
              value={maxUsd}
              onChange={(e) => setMaxUsd(e.target.value)}
              className="max-w-32"
            />
          </Field>
          <Field id="max-findings" label="Most findings">
            <Input
              id="max-findings"
              type="number"
              min="1"
              max="50"
              value={maxFindings}
              onChange={(e) => setMaxFindings(e.target.value)}
              className="max-w-32"
            />
          </Field>
          <Field id="min-severity" label="Lowest severity posted">
            <select
              id="min-severity"
              className={selectClass}
              value={draft.limits.min_severity ?? "medium"}
              onChange={(e) => set("limits", { ...draft.limits, min_severity: e.target.value as Severity })}
            >
              {SEVERITIES.map((severity) => (
                <option key={severity}>{severity}</option>
              ))}
            </select>
          </Field>
          <Field id="fail-check" label="Fail the check from">
            <select
              id="fail-check"
              className={selectClass}
              value={draft.fail_check_on ?? ""}
              onChange={(e) => set("fail_check_on", (e.target.value || null) as Severity | null)}
            >
              <option value="">never</option>
              {SEVERITIES.map((severity) => (
                <option key={severity}>{severity}</option>
              ))}
            </select>
          </Field>
        </div>
      </Section>

      <Section title="Rules" hint="RULES.md: house rules the reviewer always follows. Leave empty for none.">
        <Textarea
          id="rules"
          aria-label="Rules"
          value={draft.rules}
          onChange={(e) => set("rules", e.target.value)}
          className="min-h-40 font-mono"
        />
      </Section>

      <Section title="Skills" hint="Each skill becomes skills/<name>/SKILL.md in the reviewer's folder.">
        {draft.skills.map((skill, index) => (
          <SkillEditor
            key={index}
            index={index}
            skill={skill}
            onChange={(next) => setSkill(index, next)}
            onRemove={() =>
              set(
                "skills",
                draft.skills.filter((_, i) => i !== index),
              )
            }
          />
        ))}
        <Button
          type="button"
          variant="outline"
          onClick={() => set("skills", [...draft.skills, { name: "", description: "", body: "", extra: {} }])}
        >
          Add a skill
        </Button>
        <Field id="shared" label="Shared skills" hint="Names from shared/skills/ in the reviewers repo, one per line.">
          <Textarea
            id="shared"
            value={lines(draft.shared_skills)}
            onChange={(e) => set("shared_skills", toLines(e.target.value))}
            className="font-mono"
          />
        </Field>
      </Section>

      <ErrorNotice error={propose.error} />
      {propose.data && (
        <Notice>
          {propose.data.created ? "Opened" : "Updated"} pull request #{propose.data.number}.{" "}
          <a className={link} href={propose.data.url} target="_blank" rel="noreferrer">
            Review and merge it on GitHub
          </a>{" "}
          to make the change live.
        </Notice>
      )}
      <div className="flex gap-3">
        <Button type="submit" disabled={propose.isPending}>
          {propose.isPending ? "Opening pull request…" : "Propose as a pull request"}
        </Button>
        <Link to="/reviewers" className="self-center text-sm text-muted-foreground hover:underline">
          Back to reviewers
        </Link>
      </div>
    </form>
  )
}

// /reviewers/new and /reviewers/:id/edit. Saving opens a pull request in the reviewers repo.
export function ReviewerEditPage() {
  const { id } = useParams()
  const options = useQuery({
    queryKey: ["reviewer-options"],
    queryFn: () => apiGet<ReviewerOptions>("/api/reviewers/options"),
  })
  const draft = useQuery({
    queryKey: ["reviewer-draft", id],
    queryFn: () => apiGet<ReviewerDraft>(`/api/reviewers/${id}/draft`),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
  const initial = id ? draft.data : options.data && blank(options.data.accounts[0] ?? "")

  return (
    <section className="max-w-3xl">
      <PageHeader eyebrow="Reviewers" title={id ? `Edit ${draft.data?.name ?? "reviewer"}` : "New reviewer"}>
        Saving opens a pull request in your reviewers repo. The change goes live when someone merges it.
      </PageHeader>
      <ErrorNotice error={options.error ?? draft.error} />
      {options.data && options.data.accounts.length === 0 && (
        <Notice tone="error">Install the Chakshu app on an organization first.</Notice>
      )}
      {options.data && initial && (
        <Card>
          <CardContent>
            <ReviewerForm key={id ?? "new"} initial={initial} reviewerId={id} options={options.data} />
          </CardContent>
        </Card>
      )}
    </section>
  )
}
