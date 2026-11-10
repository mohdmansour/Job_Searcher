import type { TailorBatch } from './tailor-state'

/**
 * Ids of the user's current CV and runs, kept in the browser because phones often reload
 * background tabs. Never holds CV text. Ids act as access tokens, so they stay out of URLs.
 *
 * The data belongs to one signed-in account (`owner`, Clerk's user id). Another account on
 * the same browser starts empty, and signing out clears it.
 */

export type CvFile = {
  id: string
  name: string
  sizeKb: number
  language: 'en' | 'ar'
  extraction: 'text' | 'ocr'
}

export type SearchParams = {
  title: string
  moreTitles?: string[]
  country: string
  cities: string[]
  remote: boolean
  count: number
}

export type SessionData = {
  cv: CvFile | null
  search: SearchParams | null
  runId: string | null
  selected: string[]
  batches: TailorBatch[]
}

type Stored = SessionData & { owner: string }

const KEY = 'candor.session.v1'

export const emptySession: SessionData = {
  cv: null,
  search: null,
  runId: null,
  selected: [],
  batches: [],
}

/** What this account saved earlier. Anything saved by someone else is removed, not shown. */
export function loadSession(owner: string): SessionData {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return emptySession
    const { owner: savedBy, ...data } = JSON.parse(raw) as Partial<Stored>
    if (savedBy !== owner) {
      clearSession()
      return emptySession
    }
    return { ...emptySession, ...data }
  } catch {
    return emptySession // private window, blocked storage, or a damaged value
  }
}

export function saveSession(owner: string, data: SessionData): void {
  try {
    const stored: Stored = { ...data, owner }
    localStorage.setItem(KEY, JSON.stringify(stored))
  } catch {
    // The site still works for this visit; it just won't survive a reload.
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // nothing stored, or storage is blocked
  }
}
