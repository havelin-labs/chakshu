import { describe, expect, it } from "vitest"

import { apiQuery, initials, pageList, readParams, sortLabel, writeParams } from "@/lib/people"

describe("directory URL params", () => {
  it("leaves defaults out of the URL", () => {
    expect(writeParams(readParams(new URLSearchParams())).toString()).toBe("")
    expect(writeParams(readParams(new URLSearchParams("days=30&sort=name&order=asc&page=1"))).toString()).toBe("")
  })

  it("round-trips every param", () => {
    const query = "days=90&repo_id=r1&reviewer=security&trigger=auto&q=mona&role=owner&activity=none&sort=cost&order=asc&view=table&page=3&page_size=48"
    expect(writeParams(readParams(new URLSearchParams(query))).toString()).toBe(query)
  })

  it("orders by name ascending and everything else descending unless told otherwise", () => {
    expect(readParams(new URLSearchParams("sort=requested")).order).toBe("desc")
    expect(writeParams(readParams(new URLSearchParams("sort=requested&order=desc"))).toString()).toBe("sort=requested")
  })

  it("ignores values it doesn't know", () => {
    const params = readParams(new URLSearchParams("days=12&sort=rank&page=-2&page_size=1000&view=cards"))
    expect(params).toMatchObject({ days: 30, sort: "name", page: 1, page_size: 24, view: null })
  })

  it("keeps the view out of API calls", () => {
    expect(apiQuery(readParams(new URLSearchParams("view=table&q=x")))).toBe("q=x")
  })
})

describe("wording", () => {
  it("labels only non-name sorts and never as a rank", () => {
    expect(sortLabel("name", "asc")).toBeNull()
    expect(sortLabel("cost", "desc")).toBe("Sorted by cost of requests, highest first")
    expect(sortLabel("last_activity", "desc")).toBe("Sorted by last activity, most recent first")
  })

  it("makes initials from the name or the login", () => {
    expect(initials("Mona Lisa", "monalisa")).toBe("ML")
    expect(initials(null, "octocat")).toBe("OC")
  })

  it("offers the first, last and neighboring pages", () => {
    expect(pageList(1, 1)).toEqual([1])
    expect(pageList(5, 9)).toEqual([1, "gap", 4, 5, 6, "gap", 9])
  })
})
