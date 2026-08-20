/**
 * Measurement React Query hooks (Module 8).
 *
 * Provides mutations for creating measurements and queries for listing them.
 * Measurements are computed on demand from original + follow-up scans.
 */
import { useMutation, useQuery } from '@tanstack/react-query'

import {
  measurementService,
  type ImprovementMeasurement,
} from '@/services/measurementService'

/** Create a measurement comparing original scan vs follow-up scan. */
export function useCreateMeasurement() {
  return useMutation<ImprovementMeasurement, Error, { remediationId: string; followupScanId: string }>({
    mutationFn: ({ remediationId, followupScanId }) =>
      measurementService.createMeasurement(remediationId, followupScanId),
  })
}

/** List all measurements for a remediation. */
export function useMeasurements(remediationId: string | undefined) {
  return useQuery<ImprovementMeasurement[], Error>({
    queryKey: ['measurements', remediationId],
    queryFn: () => measurementService.listMeasurements(remediationId as string),
    enabled: !!remediationId,
  })
}

/** Get a specific measurement by ID. */
export function useMeasurement(measurementId: string | undefined) {
  return useQuery<ImprovementMeasurement, Error>({
    queryKey: ['measurement', measurementId],
    queryFn: () => measurementService.getMeasurement(measurementId as string),
    enabled: !!measurementId,
  })
}
