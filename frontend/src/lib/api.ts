// One place for talking to the Chakshu API, so every page handles errors the same way.

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(response.status, body.detail ?? response.statusText)
  }
  return body as T
}

export type Health = { status: string; version: string }
export type Ready = { status: "ok" | "unavailable"; detail?: string }
