import { EmptyState } from "@/components/people/empty-state"
import { Button, buttonVariants } from "@/components/ui/button"
import type { HiddenReason } from "@/lib/api"

// Why people's usage isn't shown, and the one thing that would show it.
export function HiddenState({
  reason,
  minGroup,
  isAdmin,
  onWiden,
  settingsHref = "#privacy",
}: {
  reason: HiddenReason
  minGroup: number
  isAdmin: boolean
  onWiden?: () => void
  settingsHref?: string
}) {
  if (reason === "names_off") {
    return (
      <EmptyState
        title="Names are turned off for analytics. Individual usage isn't shown."
        action={
          isAdmin && (
            <a className={buttonVariants({ variant: "outline", size: "sm" })} href={settingsHref}>
              Open analytics settings
            </a>
          )
        }
      />
    )
  }
  return (
    <EmptyState
      title={`Fewer than ${minGroup} people used Chakshu in this slice, so it's hidden for privacy.`}
      reason={
        isAdmin && (
          <>
            The smallest group shown is set under{" "}
            <a className="text-brand-teal-ink hover:underline" href={settingsHref}>
              Privacy
            </a>
            .
          </>
        )
      }
      action={
        onWiden && (
          <Button size="sm" variant="outline" onClick={onWiden}>
            Widen the period
          </Button>
        )
      }
    />
  )
}
