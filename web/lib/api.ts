/** The only code that talks to the backend. Requests go to /api/*, which Next.js forwards. */

const BASE = '/api'

// ---------------- response shapes (mirrors src/jobcv/api/app.py) ----------------
export type RunStatus = 'queued' | 'running' | 'done' | 'failed' | 'stopped_cost_cap'

export type Estimate = {
  apify_usd: number
  llm_usd: number
  total_usd: number
  cap_usd: number
  within_cap: boolean
}
export type PricedEstimate = Estimate & { price_to_user_usd: number }

/** The signed-in account's free allowance. Owner accounts are `unlimited`. */
export type Me = {
  user_id: string
  free_searches_left: number
  free_tailors_left: number
  unlimited: boolean
  free_max_results: number
}

export type CvInfo = { cv_id: string; language: 'en' | 'ar'; extraction: 'text' | 'ocr' }

export type Job = {
  id: string
  source: string
  title: string
  company: string
  location: string
  remote: boolean
  description: string
  url: string
  posted_at: string | null
  fetched_at: string
  language: 'en' | 'ar' | 'other'
}
export type Match = { score: number; reasons: string[]; matched_skills: string[]; gaps: string[] }
export type RankedJob = { job: Job; match: Match | null; error: string | null }

export type RunStarted = { run_id: string; status: RunStatus; estimate: Estimate }

export type SearchRun = {
  run_id: string
  status: RunStatus
  estimate: Estimate
  last_updated: string | null
  from_cache: boolean | null
  jobs: RankedJob[]
  error: string | null
}

export type Violation = { adapted_text: string; problem: string; explanation: string; suggested_fix: string }
/** fixed: language corrected only; reworded: changed for the job; moved: same text, new place. */
export type ChangeKind = 'fixed' | 'reworded' | 'moved'
export type ChangeLogEntry = { original: string; adapted: string; why_faithful: string; kind?: ChangeKind }
export type TailoredJob = {
  job_id: string
  pdf_url: string
  review_status: string
  attempts: number
  warning: boolean
  remaining_violations: Violation[]
  change_log: ChangeLogEntry[]
  suggestions?: string[] // what only the user can add, such as missing dates
}
export type TailorRun = {
  tailor_id: string
  status: RunStatus
  estimate: Estimate
  results: TailoredJob[]
  error: string | null
}

export type SearchForm = { country: string; cities: string[]; remote: boolean; max_results: number }
export type SearchRequest = SearchForm & { cv_id: string; title: string; more_titles?: string[]; force_refresh?: boolean }
export type TailorRequest = { run_id: string; job_ids: string[]; user_extra_info?: string }

// ---------------- errors ----------------
export type ApiErrorCode =
  | 'unauthorized' // 401: not signed in, or the session ended
  | 'rejected' // 400, 422: the backend refused the input
  | 'cost_cap' // 402
  | 'expired' // 404: not found, or deleted after the retention period
  | 'too_large' // 413
  | 'unavailable' // 503: e.g. OCR isn't installed
  | 'allowance_used' // 403: the free allowance is used up
  | 'free_limit' // 403: more than a free account may ask for
  | 'rate_limited' // 429: one run at a time, or too many uploads today
  | 'daily_budget' // 429: free use is paused for the rest of the day
  | 'server' // anything else
  | 'network' // no response at all

export class ApiError extends Error {
  constructor(readonly code: ApiErrorCode) {
    super(code)
    this.name = 'ApiError'
  }
}

function codeForStatus(status: number): ApiErrorCode {
  if (status === 401) return 'unauthorized'
  if (status === 400 || status === 422) return 'rejected'
  if (status === 402) return 'cost_cap'
  if (status === 404) return 'expired'
  if (status === 413) return 'too_large'
  if (status === 503) return 'unavailable'
  return 'server'
}

// ---------------- who is calling ----------------
let getSessionToken: () => Promise<string | null> = async () => null
let onSignedOut: () => void = () => {}

/** The Clerk hooks live in React; this hands the request code what it needs from them. */
export function connectAuth(getToken: () => Promise<string | null>, signedOut: () => void): void {
  getSessionToken = getToken
  onSignedOut = signedOut
}

async function authHeaders(): Promise<Record<string, string>> {
  try {
    const token = await getSessionToken() // Clerk returns a fresh one when the last has expired
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    throw new ApiError('network')
  }
}

const LIMIT_CODES: readonly ApiErrorCode[] = ['allowance_used', 'free_limit', 'rate_limited', 'daily_budget']

/** 403 and 429 say which limit was reached: `{"detail": {"code": ...}}`. */
function limitCode(body: unknown): ApiErrorCode | null {
  const code = (body as { detail?: { code?: unknown } } | null)?.detail?.code
  return LIMIT_CODES.find((c) => c === code) ?? null
}

function errorFor(status: number, body?: unknown): ApiError {
  if (status === 401) onSignedOut()
  return new ApiError(limitCode(body) ?? codeForStatus(status))
}

// ---------------- requests ----------------
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await authHeaders()
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { cache: 'no-store', ...init, headers: { ...init?.headers, ...auth } })
  } catch {
    throw new ApiError('network')
  }
  if (!res.ok) throw errorFor(res.status, await res.json().catch(() => null))
  return (res.status === 204 ? undefined : await res.json()) as T
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

const id = encodeURIComponent

/** XHR rather than fetch: it reports upload progress, so the UI can tell sending from reading. */
async function uploadCv(file: File, onSent?: () => void): Promise<CvInfo> {
  const auth = await authHeaders()
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/cv`)
    for (const [name, value] of Object.entries(auth)) xhr.setRequestHeader(name, value)
    xhr.responseType = 'json'
    xhr.upload.onload = () => onSent?.()
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as CvInfo)
      else reject(errorFor(xhr.status, xhr.response))
    }
    xhr.onerror = () => reject(new ApiError('network'))
    xhr.ontimeout = () => reject(new ApiError('network'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

/** PDF links can't carry a header, so they use Clerk's session cookie: bring it up to date. */
export async function refreshSession(): Promise<void> {
  await getSessionToken().catch(() => null) // a problem here shows up as the download's own error
}

export const api = {
  me: () => request<Me>('/me'),
  deleteMyData: () => request<void>('/me/data', { method: 'DELETE' }),
  uploadCv,
  getCv: (cvId: string) => request<CvInfo>(`/cv/${id(cvId)}`),
  deleteCv: (cvId: string) => request<void>(`/cv/${id(cvId)}`, { method: 'DELETE' }),
  estimateSearch: (form: SearchForm) => post<PricedEstimate>('/estimate/search', form),
  estimateTailor: (nJobs: number) => post<PricedEstimate>('/estimate/tailor', { n_jobs: nJobs }),
  startSearch: (req: SearchRequest) => post<RunStarted>('/search', req),
  getRun: (runId: string) => request<SearchRun>(`/runs/${id(runId)}`),
  startTailor: (req: TailorRequest) => post<RunStarted>('/tailor', req),
  getTailor: (tailorId: string) => request<TailorRun>(`/tailor/${id(tailorId)}`),
}

/** The backend returns an absolute address; the browser must use the website's proxy. */
export function pdfHref(pdfUrl: string): string {
  return `${BASE}${new URL(pdfUrl).pathname}`
}

// ---------------- polling ----------------
export const isFinished = (status: string) => status !== 'queued' && status !== 'running'

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      resolve()
    }, { once: true })
  })
}

/** Phones freeze hidden tabs, so wait for the page to be visible again instead of polling. */
function whenVisible(signal?: AbortSignal): Promise<void> {
  if (typeof document === 'undefined' || !document.hidden) return Promise.resolve()
  return new Promise((resolve) => {
    const done = () => {
      document.removeEventListener('visibilitychange', onChange)
      resolve()
    }
    const onChange = () => {
      if (!document.hidden) done()
    }
    document.addEventListener('visibilitychange', onChange)
    signal?.addEventListener('abort', done, { once: true })
  })
}

type PollOptions = { intervalMs?: number; signal?: AbortSignal; maxTransientErrors?: number }

/** The run may still be going on the server: these say nothing about the run itself. */
export const isConnectionProblem = (code: ApiErrorCode | undefined) => code === 'network' || code === 'server'

/** Calls fetcher until finished. Survives outages of a few minutes; other errors are thrown. */
export async function poll<T>(
  fetcher: () => Promise<T>,
  finished: (value: T) => boolean,
  onUpdate: (value: T) => void,
  { intervalMs = 2000, signal, maxTransientErrors = 150 }: PollOptions = {},
): Promise<T | undefined> {
  let transientErrors = 0
  while (!signal?.aborted) {
    await whenVisible(signal)
    if (signal?.aborted) return undefined
    try {
      const value = await fetcher()
      transientErrors = 0
      if (signal?.aborted) return undefined
      onUpdate(value)
      if (finished(value)) return value
    } catch (e) {
      if (!(e instanceof ApiError) || !isConnectionProblem(e.code) || ++transientErrors >= maxTransientErrors) throw e
    }
    await sleep(intervalMs, signal)
  }
  return undefined
}
