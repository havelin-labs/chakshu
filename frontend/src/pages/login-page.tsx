import { Navigate, useSearchParams } from "react-router-dom"

import { Notice } from "@/components/notice"
import { PageHeader } from "@/components/page-header"
import { buttonVariants } from "@/components/ui/button"
import { useSession } from "@/hooks/use-session"

const ERRORS: Record<string, string> = {
  "not-a-member":
    "That GitHub account isn't a member of an organization this Chakshu serves. Ask an org owner to add you, or sign in with another account.",
}

export function LoginPage() {
  const { data: session } = useSession()
  const [params] = useSearchParams()
  const error = ERRORS[params.get("error") ?? ""]

  if (!session) return null
  if (!session.configured) return <Navigate to="/setup" replace />
  if (session.user) return <Navigate to="/" replace />

  return (
    <section className="max-w-xl">
      <PageHeader eyebrow="Sign in" title="Pull request reviews for your teams">
        Sign in with the GitHub account you use for work. Chakshu shows the reviewers and runs for your organization.
      </PageHeader>
      <div className="space-y-4">
        {error && <Notice tone="error">{error}</Notice>}
        <a className={buttonVariants({ size: "lg" })} href="/auth/login">
          Sign in with GitHub
        </a>
      </div>
    </section>
  )
}
