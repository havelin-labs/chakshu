import { LayoutGridIcon, ListIcon, SearchIcon } from "lucide-react"

import { FilterBar, type SliceKey } from "@/components/analytics-filters"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { PeopleResult } from "@/lib/api"
import {
  ACTIVITIES,
  ACTIVITY_LABEL,
  apiQuery,
  hasFilters,
  PERIODS,
  ROLE_LABEL,
  ROLES,
  SORT_LABEL,
  SORTS,
  sortLabel,
  type DirectoryParams,
  type Order,
  type Sort,
  type View,
} from "@/lib/people"

export function PeopleToolbar({
  params,
  view,
  search,
  counts,
  onSearch,
  onChange,
  onSlice,
  onView,
  onClear,
}: {
  params: DirectoryParams
  view: View
  search: string
  counts: PeopleResult["counts"]
  onSearch: (text: string) => void
  onChange: (changes: Partial<DirectoryParams>) => void
  onSlice: (key: SliceKey, value: string | null) => void
  onView: (view: View) => void
  onClear: () => void
}) {
  const label = sortLabel(params.sort, params.order)
  const activityItems = ACTIVITIES.map((a) => ({
    value: a,
    label: counts ? `${ACTIVITY_LABEL[a]} (${counts[a === "all" ? "all" : a]})` : ACTIVITY_LABEL[a],
  }))
  const roleItems = ROLES.map((r) => ({ value: r, label: ROLE_LABEL[r] }))
  const query = apiQuery(params)
  return (
    <div className="space-y-3">
      <FilterBar
        slice={{ days: params.days, repoId: params.repo_id, reviewer: params.reviewer, trigger: params.trigger }}
        periods={PERIODS}
        onChange={onSlice}
      />
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <SearchIcon aria-hidden="true" className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Search people by name or login"
            placeholder="Search name or login"
            className="pl-8"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
          />
        </div>
        <Select
          items={roleItems}
          value={params.role}
          onValueChange={(value) => value && onChange({ role: value as DirectoryParams["role"] })}
        >
          <SelectTrigger aria-label="Role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {roleItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          items={activityItems}
          value={params.activity}
          onValueChange={(value) => value && onChange({ activity: value as DirectoryParams["activity"] })}
        >
          <SelectTrigger aria-label="Activity">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {activityItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" />}>Sort: {SORT_LABEL[params.sort]}</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuGroup>
              <DropdownMenuLabel>Sort by</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={params.sort} onValueChange={(sort: Sort) => onChange({ sort })}>
                {SORTS.map((s) => (
                  <DropdownMenuRadioItem key={s} value={s} closeOnClick>
                    {SORT_LABEL[s]}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel>Order</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={params.order} onValueChange={(order: Order) => onChange({ order })}>
                <DropdownMenuRadioItem value="asc" closeOnClick>Ascending</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="desc" closeOnClick>Descending</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <ToggleGroup aria-label="Layout" value={[view]} onValueChange={(value) => value[0] && onView(value[0] as View)}>
          <ToggleGroupItem value="grid" aria-label="Grid">
            <LayoutGridIcon aria-hidden="true" />
            <span className="hidden sm:inline">Grid</span>
          </ToggleGroupItem>
          <ToggleGroupItem value="table" aria-label="Table">
            <ListIcon aria-hidden="true" />
            <span className="hidden sm:inline">Table</span>
          </ToggleGroupItem>
        </ToggleGroup>
        {hasFilters(params) && (
          <Button variant="ghost" onClick={onClear}>
            Clear filters
          </Button>
        )}
        <a
          className={buttonVariants({ variant: "outline", className: "sm:ml-auto" })}
          href={`/api/analytics/people.csv${query ? `?${query}` : ""}`}
        >
          Export CSV
        </a>
      </div>
      {label && <p className="text-xs text-muted-foreground">{label}</p>}
    </div>
  )
}
