/**
 * Strategy generation React Query hook (Module 4).
 *
 * Generation is on-demand and not persisted (by design — the persistence
 * design belongs to later evaluation/ranking modules), so this is a simple
 * mutation with no query cache to invalidate.
 */
import { useMutation } from '@tanstack/react-query'

import {
  strategyService,
  type GenerateStrategiesInput,
  type StrategyGeneration,
} from '@/services/strategyService'

/** Generate candidate strategies for an issue or group of a scan. */
export function useGenerateStrategies(scanId: string | undefined) {
  return useMutation<StrategyGeneration, Error, GenerateStrategiesInput>({
    mutationFn: (input) =>
      strategyService.generateStrategies(scanId as string, {
        issueId: input.issueId,
        groupId: input.groupId,
        strategyCount: input.strategyCount ?? 3,
      }),
  })
}
