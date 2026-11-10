import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = join(__dirname, '..')
const FAKE = ['Layla', 'Haddad', 'Nimbus', 'Souqly', 'Falcon Ledger', 'Qarar', 'Meridian Cloud', 'Orbit Mobility', 'Brightline', 'Corvid', 'lib/data', 'lib/pdf', 'vercel/analytics']

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? sourceFiles(path) : /\.(tsx?|mjs)$/.test(name) ? [path] : []
  })
}

describe('prototype data', () => {
  const files = ['app', 'components', 'lib'].flatMap((d) => sourceFiles(join(ROOT, d)))

  it('finds the source files', () => expect(files.length).toBeGreaterThan(20))

  it.each(FAKE)('%s is gone', (word) => {
    expect(files.filter((f) => readFileSync(f, 'utf8').includes(word))).toEqual([])
  })
})
