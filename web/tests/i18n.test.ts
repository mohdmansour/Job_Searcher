import { describe, expect, it } from 'vitest'
import { dictionaries } from '@/lib/i18n'

function shape(value: unknown, path = ''): string[] {
  if (value === null || typeof value !== 'object') return [path]
  if (Array.isArray(value)) return [`${path}[]`]
  return Object.entries(value).flatMap(([k, v]) => shape(v, path ? `${path}.${k}` : k))
}

describe('translations', () => {
  it('Arabic and English have exactly the same keys', () => {
    expect(shape(dictionaries.ar).sort()).toEqual(shape(dictionaries.en).sort())
  })
})
