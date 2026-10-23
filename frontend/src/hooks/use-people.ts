import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  ApiError,
  apiGet,
  apiPost,
  type MembersSource,
  type PeopleResult,
  type PersonActivityPage,
  type PersonResult,
} from "@/lib/api"
import { apiQuery, sliceQuery, type DirectoryParams, type SliceParams } from "@/lib/people"

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

// Not found and not allowed won't change on a retry.
const retryServerErrors = (failures: number, error: Error) =>
  !(error instanceof ApiError && error.status < 500) && failures < 3

export function usePerson(login: string, slice: SliceParams) {
  const query = sliceQuery(slice)
  return useQuery({
    queryKey: ["analytics", "person", login, query],
    queryFn: () => apiGet<PersonResult>(`/api/analytics/people/${encodeURIComponent(login)}${query ? `?${query}` : ""}`),
    placeholderData: keepPreviousData,
    retry: retryServerErrors,
  })
}

export function usePersonActivity(login: string, slice: SliceParams, enabled: boolean) {
  const query = sliceQuery(slice)
  return useInfiniteQuery({
    queryKey: ["analytics", "person-activity", login, query],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams(query)
      if (pageParam) params.set("cursor", pageParam)
      return apiGet<PersonActivityPage>(`/api/analytics/people/${encodeURIComponent(login)}/activity?${params}`)
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled,
  })
}
