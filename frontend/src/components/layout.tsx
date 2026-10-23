import { NavLink, Outlet } from "react-router-dom"

import { Logo } from "@/components/logo"
import { UserMenu } from "@/components/user-menu"
import { useSession } from "@/hooks/use-session"
import { cn } from "@/lib/utils"

const NAV: { to: string; label: string; admin?: boolean }[] = [
  { to: "/", label: "Reviews" },
  { to: "/repos", label: "Repositories" },
  { to: "/reviewers", label: "Reviewers" },
  { to: "/insights", label: "Insights" },
  { to: "/analytics", label: "Analytics", admin: true },
  { to: "/me", label: "My activity" },
  { to: "/settings", label: "Settings", admin: true },
  { to: "/status", label: "Status" },
]

export function Layout() {
  const { data: session } = useSession()
  const user = session?.user

  return (
    <div className="relative min-h-svh bg-background text-foreground">
      <div className="bg-havelin-grid pointer-events-none absolute inset-0 opacity-[0.03]" aria-hidden />
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-6">
          <NavLink to="/" aria-label="Chakshu home">
            <Logo />
          </NavLink>
          {user ? (
            <div className="flex items-center gap-6">
              <nav className="hidden items-center gap-5 text-sm font-medium sm:flex">
                {NAV.filter((item) => !item.admin || user.is_admin).map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      cn("text-muted-foreground hover:text-foreground", isActive && "text-foreground")
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </nav>
              <UserMenu user={user} />
            </div>
          ) : (
            <span className="hidden text-sm font-medium text-muted-foreground sm:inline">
              Pull request reviews for your teams
            </span>
          )}
        </div>
      </header>
      <main className="relative mx-auto max-w-6xl px-6 py-16">
        <Outlet />
      </main>
      <footer className="relative border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-6 text-sm text-muted-foreground">
          <span>Chakshu, by Havelin</span>
          <a className="hover:text-foreground" href="https://chakshu.havelin.in/docs" target="_blank" rel="noreferrer">
            Docs
          </a>
        </div>
      </footer>
    </div>
  )
}
