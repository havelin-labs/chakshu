import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { apiGet, apiPost, type MembersSource, type PeopleResult } from "@/lib/api"
import { apiQuery, type DirectoryParams } from "@/lib/people"

export function usePeopleDirectory(params: DirectoryParams) {
  const query = apiQuery(params)
  return useQuery({
    queryKey: ["analytics", "people", query],
    queryFn: () => apiGet<PeopleResult>(`/api/analytics/people${query ? `?${query}` : ""}`),
    placeholderData: keepPreviousData, // keep the cards on screen while the next page or filter loads
  })
}

export function useRefreshMembers() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<{ members_source: MembersSource }>("/api/analytics/people/refresh"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["analytics", "people"] }),
  })
}
