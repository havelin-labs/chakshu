import { Outlet } from "react-router-dom"

export function Layout() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="font-semibold tracking-tight">Chakshu</span>
          <span className="text-sm text-muted-foreground">pull request reviews for your teams</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
