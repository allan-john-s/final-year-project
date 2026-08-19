/**
 * Strategy evaluation React Query hook (Module 5).
 *
 * Evaluation is on-demand and not persisted (by design — persistence belongs
 * to the later ranking/research modules), so this is a simple mutation with
 * no query cache to invalidate.
 */
import { useMutation } from '@tanstack/react-query'

import {
  evaluationService,
  type EvaluateStrategiesInput,
  type EvaluationBatch,
} from '@/services/evaluationService'

/** Evaluate the supplied candidate strategies for an issue/group of a scan. */
export function useEvaluateStrategies(scanId: string | undefined) {
  return useMutation<EvaluationBatch, Error, EvaluateStrategiesInput>({
    mutationFn: (input) => evaluationService.evaluateStrategies(scanId as string, input),
  })
}
