import { describe, expect, it } from 'vitest'
import type { RunStatus, TailoredJob, TailorRun } from '@/lib/api'
import { tailorItems, type TailorBatch } from '@/lib/tailor-state'

const job = (id: string) => ({ id, title: `T-${id}`, company: 'C' })
const batch: TailorBatch = { id: 'b', searchRunId: 's', jobs: [job('1'), job('2'), job('3')] }
const result = (id: string) => ({ job_id: id, pdf_url: 'http://x/f', review_status: 'PASS' }) as TailoredJob
const run = (status: RunStatus, ...done: string[]) =>
  ({ tailor_id: 'b', status, results: done.map(result) }) as unknown as TailorRun
const statuses = (r?: TailorRun, error?: Parameters<typeof tailorItems>[2][string]) =>
  tailorItems([batch], { b: r }, { b: error }).map((i) => i.status)

describe('tailorItems', () => {
  it('waits until the first status arrives', () => expect(statuses()).toEqual(['waiting', 'waiting', 'waiting']))
  it('a queued run waits', () => expect(statuses(run('queued'))).toEqual(['waiting', 'waiting', 'waiting']))
  it('marks only the next unfinished job as working', () => {
    expect(statuses(run('running', '1'))).toEqual(['done', 'working', 'waiting'])
  })
  it('all done', () => expect(statuses(run('done', '1', '2', '3'))).toEqual(['done', 'done', 'done']))
  it('keeps finished jobs when the run fails', () => {
    expect(statuses(run('failed', '1'))).toEqual(['done', 'failed', 'failed'])
  })
  it('keeps finished jobs when the cost cap stops the run', () => {
    expect(statuses(run('stopped_cost_cap', '1'))).toEqual(['done', 'stopped', 'stopped'])
  })
  it('an expired run has nothing left, even previously finished jobs', () => {
    expect(statuses(run('done', '1', '2', '3'), 'expired')).toEqual(['expired', 'expired', 'expired'])
  })
  it('a lost connection keeps finished jobs and reports the rest', () => {
    const items = tailorItems([batch], { b: run('running', '1') }, { b: 'network' })
    expect(items.map((i) => i.status)).toEqual(['done', 'error', 'error'])
    expect(items[1].errorCode).toBe('network')
  })
})
