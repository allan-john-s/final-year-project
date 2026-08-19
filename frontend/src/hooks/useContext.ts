/**
 * Context React Query hook.
 *
 * Follows the useScans convention: data fetching is centralized here. Context
 * is deterministic and generated on demand — a plain query with no polling
 * (a completed scan's context never changes).
 */
import { useQuery } from '@tanstack/react-query'

import { contextService } from '@/services/contextService'

export function contextKey(scanId: string) {
  return ['scans', scanId, 'context'] as const
}

/** Fetch the context document for a scan (enabled once a scan id exists). */
export function useContextDocument(scanId: string | undefined) {
  return useQuery({
    queryKey: contextKey(scanId ?? ''),
    queryFn: () => contextService.getContext(scanId as string),
    enabled: Boolean(scanId),
  })
}
