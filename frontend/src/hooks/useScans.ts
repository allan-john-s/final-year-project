/**
 * Scan React Query hooks.
 *
 * Follows the useProjects convention: data fetching is centralized here.
 * Active scans (PENDING/RUNNING) are polled via `refetchInterval` so the UI
 * reflects PENDING → RUNNING → COMPLETED/FAILED without manual refresh;
 * terminal scans stop polling.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { scanService, type Scan, type ScannerType } from '@/services/scanService'

export const userScansKey = ['scans'] as const

export function projectScansKey(projectId: string) {
  return ['projects', projectId, 'scans'] as const
}

export function scanKey(id: string) {
  return ['scans', id] as const
}

export function scanIssuesKey(id: string) {
  return ['scans', id, 'issues'] as const
}

function isActive(scan: Scan | undefined): boolean {
  return scan !== undefined && (scan.status === 'PENDING' || scan.status === 'RUNNING')
}

const POLL_MS = 2500

/** Fetch all scans owned by the current user, polling while any are active. */
export function useScans() {
  return useQuery({
    queryKey: userScansKey,
    queryFn: () => scanService.listScans(),
    refetchInterval: (query) => {
      const data = query.state.data as Scan[] | undefined
      return data?.some(isActive) ? POLL_MS : false
    },
  })
}

/** Fetch a single scan, polling while it is still running. */
export function useScan(id: string | undefined) {
  return useQuery({
    queryKey: scanKey(id ?? ''),
    queryFn: () => scanService.getScan(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => (isActive(query.state.data as Scan | undefined) ? POLL_MS : false),
  })
}

/** Fetch a project's scans, polling while any of them is still running. */
export function useProjectScans(projectId: string | undefined) {
  return useQuery({
    queryKey: projectScansKey(projectId ?? ''),
    queryFn: () => scanService.listProjectScans(projectId as string),
    enabled: Boolean(projectId),
    refetchInterval: (query) => {
      const data = query.state.data as Scan[] | undefined
      return data?.some(isActive) ? POLL_MS : false
    },
  })
}

/** Fetch a scan's normalized accessibility issues. */
export function useScanIssues(scanId: string | undefined) {
  return useQuery({
    queryKey: scanIssuesKey(scanId ?? ''),
    queryFn: () => scanService.getIssues(scanId as string),
    enabled: Boolean(scanId),
  })
}

/** Start a scan for a project, then refresh the project + its scans. */
export function useStartScan(projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (scannerType: ScannerType = 'AXE') =>
      scanService.startScan(projectId as string, scannerType),
    onSuccess: () => {
      if (!projectId) return
      void queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
      void queryClient.invalidateQueries({ queryKey: projectScansKey(projectId) })
    },
  })
}

/** Delete a scan, then refresh every scans list. */
export function useDeleteScan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => scanService.deleteScan(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userScansKey })
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
