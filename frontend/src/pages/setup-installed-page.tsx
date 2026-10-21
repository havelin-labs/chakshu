import { useQuery } from "@tanstack/react-query"

import { ErrorNotice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useSession } from "@/hooks/use-session"
import { apiPost } from "@/lib/api"

// GitHub sends people here after they install the app (the manifest's setup_url).
export function SetupInstalledPage() {
  const { data: session } = useSession()
  const sync = useQuery({
    queryKey: ["setup-sync"],
    queryFn: () => apiPost<{ installations: number }>("/api/setup/sync"),
    enabled: Boolean(session?.csrf_token),
    retry: false,
    staleTime: Infinity,
  })

  return (
    <section className="max-w-2xl">
      <PageHeader eyebrow="Step 3 of 3" title="App installed">
        Chakshu is reading the repositories you gave it access to.
      </PageHeader>
      <Card>
        <CardContent className="space-y-4 py-2">
          {sync.isPending && <p className="text-muted-foreground">Syncing installations…</p>}
          <ErrorNotice error={sync.error} />
          {sync.data && (
            <>
              <p>
                Found {sync.data.installations} installation{sync.data.installations === 1 ? "" : "s"}. Sign in with
                the GitHub account that owns the organization to finish.
              </p>
              <div className="flex flex-wrap gap-3">
                <a className={buttonVariants()} href="/auth/login">
                  Sign in with GitHub
                </a>
                {session?.app && (
                  <a className={buttonVariants({ variant: "outline" })} href={session.app.install_url}>
                    Change repository access
                  </a>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
