/**
 * Strategy ranking React Query hook (Module 6).
 *
 * Ranking is on-demand and not persisted (by design — persistence belongs
 * to later research modules), so this is a simple mutation with no query
 * cache to invalidate.
 */
import { useMutation } from '@tanstack/react-query'

import {
  rankingService,
  type RankStrategiesInput,
  type RankingBatch,
} from '@/services/rankingService'

/** Rank evaluated candidate strategies for an issue/group of a scan. */
export function useRankStrategies(scanId: string | undefined) {
  return useMutation<RankingBatch, Error, RankStrategiesInput>({
    mutationFn: (input) => rankingService.rankStrategies(scanId as string, input),
  })
}
