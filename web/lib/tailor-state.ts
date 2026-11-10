import type { ApiErrorCode, TailoredJob, TailorRun } from './api'

export type TailorJobRef = { id: string; title: string; company: string }
/** One POST /tailor. `searchRunId` is kept so a job can be retried later. */
export type TailorBatch = { id: string; searchRunId: string; jobs: TailorJobRef[] }

export type ItemStatus = 'waiting' | 'working' | 'done' | 'failed' | 'stopped' | 'expired' | 'error'

export type TailorItem = {
  job: TailorJobRef
  batchId: string
  status: ItemStatus
  result?: TailoredJob
  errorCode?: ApiErrorCode
}

/** The backend works through a batch in order and reports a job only once it has finished. */
export function tailorItems(
  batches: TailorBatch[],
  runs: Record<string, TailorRun | undefined>,
  errors: Record<string, ApiErrorCode | undefined>,
): TailorItem[] {
  return batches.flatMap((batch) => {
    const run = runs[batch.id]
    const error = errors[batch.id]
    let workingAssigned = false
    return batch.jobs.map((job): TailorItem => {
      const base = { job, batchId: batch.id }
      const result = run?.results.find((r) => r.job_id === job.id)
      if (error === 'expired') return { ...base, status: 'expired' }
      if (result) return { ...base, status: 'done', result }
      if (error) return { ...base, status: 'error', errorCode: error }
      if (!run || run.status === 'queued') return { ...base, status: 'waiting' }
      if (run.status === 'running') {
        if (workingAssigned) return { ...base, status: 'waiting' }
        workingAssigned = true
        return { ...base, status: 'working' }
      }
      return { ...base, status: run.status === 'stopped_cost_cap' ? 'stopped' : 'failed' }
    })
  })
}
