import { useMutation } from "@tanstack/react-query"

import { ErrorNotice, Notice } from "@/components/notice"
import { Button } from "@/components/ui/button"
import { apiPost } from "@/lib/api"

type ReviewerTeams = { created: string[]; removed: string[]; kept: string[]; error: string | null }
type TeamResult = { team: string; results: Record<string, string>; reviewer_teams: Record<string, ReviewerTeams> }

const describe = (state: string) =>
  state === "created" ? "created" : state === "exists" ? "already there" : `not created: ${state}`

// The empty team people mention (@org/chakshu), plus a child team per reviewer (chakshu-<name>) so each
// reviewer can be picked in a pull request's Reviewers box.
export function ReviewTeam() {
  const create = useMutation({ mutationFn: () => apiPost<TeamResult>("/api/setup/team") })
  const results = Object.entries(create.data?.results ?? {})
  const failed = results.some(([, state]) => state.startsWith("failed"))

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        People ask for a review by mentioning <code className="font-mono">@&lt;org&gt;/chakshu</code> or requesting it as
        a reviewer. That needs an empty team called chakshu in each organization, with read access to the repositories.
        Each reviewer also gets its own team under it, like <code className="font-mono">chakshu-security</code>, so you
        can pick one reviewer in a pull request's Reviewers box. Reviewer teams follow the reviewers repo on every sync.
      </p>
      <Button variant="outline" onClick={() => create.mutate()} disabled={create.isPending}>
        {create.isPending ? "Creating…" : "Create the chakshu teams"}
      </Button>
      <ErrorNotice error={create.error} />
      {create.data && (
        <Notice tone={failed ? "error" : undefined}>
          {results.length === 0 && "No organizations are installed yet."}
          {results.map(([account, state]) => (
            <span key={account} className="block">
              @{account}/{create.data.team}: {describe(state)}
            </span>
          ))}
          {Object.entries(create.data.reviewer_teams ?? {}).map(([account, r]) => (
            <span key={`${account}-reviewers`} className="block">
              {r.error
                ? `Reviewer teams in ${account}: not synced, ${r.error}`
                : `Reviewer teams in ${account}: ${r.created.length} created, ${r.kept.length} already there, ${r.removed.length} removed`}
            </span>
          ))}
          {failed && (
            <span className="mt-2 block">
              The app needs the members: write permission. Settings shows what's missing.
            </span>
          )}
        </Notice>
      )}
    </div>
  )
}
