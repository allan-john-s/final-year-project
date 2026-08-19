/**
 * Remediation React Query hooks (Module 7).
 *
 * Provides mutations for generating remediation proposals and updating
 * their status. Proposals are persisted in the backend (in-memory store
 * for development) and can be retrieved by ID or listed per scan.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  remediationService,
  type GenerateRemediationInput,
  type RemediationProposal,
  type RemediationStatus,
} from '@/services/remediationService'

/** Generate a remediation proposal for the top-ranked strategy. */
export function useGenerateRemediation(scanId: string | undefined) {
  return useMutation<RemediationProposal, Error, GenerateRemediationInput>({
    mutationFn: (input) => remediationService.generateRemediation(scanId as string, input),
  })
}

/** Get a specific remediation proposal by ID. */
export function useRemediation(proposalId: string | undefined) {
  return useQuery<RemediationProposal, Error>({
    queryKey: ['remediation', proposalId],
    queryFn: () => remediationService.getRemediation(proposalId as string),
    enabled: !!proposalId,
  })
}

/** List all remediation proposals for a scan. */
export function useRemediations(scanId: string | undefined) {
  return useQuery<RemediationProposal[], Error>({
    queryKey: ['remediations', scanId],
    queryFn: () => remediationService.listRemediations(scanId as string),
    enabled: !!scanId,
  })
}

/** Update a proposal's status. */
export function useUpdateRemediationStatus(scanId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation<RemediationProposal, Error, { proposalId: string; status: RemediationStatus }>({
    mutationFn: ({ proposalId, status }) =>
      remediationService.updateStatus(proposalId, status),
    onSuccess: () => {
      if (scanId) {
        void queryClient.invalidateQueries({ queryKey: ['remediations', scanId] })
      }
    },
  })
}
