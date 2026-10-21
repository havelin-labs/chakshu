import { Outlet } from "react-router-dom"

import { Logo } from "@/components/logo"

export function Layout() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <div className="bg-brand-gradient h-1" aria-hidden />
      <header className="border-b">
        <div className="mx-auto flex h-16 max-w-5xl items-center gap-4 px-4">
          <Logo />
          <span className="hidden text-sm text-muted-foreground sm:inline">pull request reviews for your teams</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
