const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
]
const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" })

export function timeAgo(iso: string): string {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return "just now"
}

export function cost(usd: number | null): string {
  return usd == null ? "—" : `$${usd.toFixed(usd < 1 ? 3 : 2)}`
}

export function duration(ms: number | null): string {
  if (ms == null) return "—"
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export const shortSha = (sha: string) => sha.slice(0, 7)

export function percent(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`
}

export function count(value: number | null): string {
  return value == null ? "—" : value.toLocaleString("en")
}