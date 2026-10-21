import { Outlet } from "react-router-dom"

import { Logo } from "@/components/logo"

export function Layout() {
  return (
    <div className="relative min-h-svh bg-background text-foreground">
      <div className="bg-havelin-grid pointer-events-none absolute inset-0 opacity-[0.03]" aria-hidden />
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo />
          <span className="hidden text-sm font-medium text-muted-foreground sm:inline">
            Pull request reviews for your teams
          </span>
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
