import { describe, expect, it } from 'vitest'
import { daysAgo, formatUsd } from '@/lib/format'

describe('formatUsd', () => {
  it('uses one clear format', () => expect(formatUsd(0.27)).toBe('$0.27'))
  it('never shows a tiny price as free', () => expect(formatUsd(0.004)).toBe('< $0.01'))
  it('shows zero as zero', () => expect(formatUsd(0)).toBe('$0.00'))
})

describe('daysAgo', () => {
  const now = Date.parse('2026-11-08T12:00:00Z')
  it('counts whole days', () => expect(daysAgo('2026-11-05T11:00:00Z', now)).toBe(3))
  it('the same day is zero', () => expect(daysAgo('2026-11-08T01:00:00Z', now)).toBe(0))
  it('a future date is zero', () => expect(daysAgo('2026-11-09T01:00:00Z', now)).toBe(0))
})
