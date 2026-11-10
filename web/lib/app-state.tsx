'use client'

import { useAuth, useClerk } from '@clerk/nextjs'
import { usePathname, useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, ApiError, connectAuth, isFinished, poll, type ApiErrorCode, type Me, type SearchRun, type TailorRun } from './api'
import { dictionaries, type Dict, type Locale } from './i18n'
import { clearSession, emptySession, loadSession, saveSession, type CvFile, type SearchParams } from './session'
import { tailorItems, type TailorBatch, type TailorItem } from './tailor-state'

export type { CvFile, SearchParams }

type AppState = {
  locale: Locale
  t: Dict
  setLocale: (l: Locale) => void
  hydrated: boolean
  // ---- real: CV ----
  cv: CvFile | null
  cvExpired: boolean
  setCv: (cv: CvFile) => void
  removeCv: () => Promise<void>
  deleteAllData: () => Promise<void>
  cvBusy: boolean
  setCvBusy: (busy: boolean) => void
  // ---- real: search ----
  search: SearchParams | null
  run: SearchRun | null
  runId: string | null
  runError: ApiErrorCode | null
  startSearch: (params: SearchParams, options?: { forceRefresh?: boolean }) => Promise<void>
  selected: string[]
  toggleSelected: (id: string) => void
  clearSelected: () => void
  // ---- real: tailoring ----
  items: TailorItem[]
  startTailor: (jobIds: string[], extraInfo: string) => Promise<void>
  retryJob: (item: TailorItem) => Promise<void>
  // ---- real: the free allowance (null until known) ----
  allowance: Me | null
  refreshAllowance: () => void
}

const Ctx = createContext<AppState | null>(null)

/** Pages that need an account. Public pages stay put if a stored session has ended. */
const APP_PAGES = /^\/(search|results|generate|account)(\/|$)/

const errorCode = (e: unknown): ApiErrorCode => (e instanceof ApiError ? e.code : 'server')

export function AppStateProvider({ initialLocale, children }: { initialLocale: Locale; children: React.ReactNode }) {
  const { getToken, isSignedIn, isLoaded, userId } = useAuth()
  const clerk = useClerk()
  const pathname = usePathname()
  const router = useRouter()
  // Set during render, not in an effect: child effects run first and may already make requests.
  connectAuth(getToken, () => {
    if (APP_PAGES.test(window.location.pathname)) clerk.redirectToSignIn({ signInForceRedirectUrl: window.location.href })
  })

  const [locale, setLocaleState] = useState<Locale>(initialLocale)
  const [hydrated, setHydrated] = useState(false)
  const [cv, setCvState] = useState<CvFile | null>(null)
  const [cvExpired, setCvExpired] = useState(false)
  const [cvBusy, setCvBusy] = useState(false)
  const [search, setSearch] = useState<SearchParams | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [run, setRun] = useState<SearchRun | null>(null)
  const [runError, setRunError] = useState<ApiErrorCode | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [batches, setBatches] = useState<TailorBatch[]>([])
  const [tailorRuns, setTailorRuns] = useState<Record<string, TailorRun | undefined>>({})
  const [tailorErrors, setTailorErrors] = useState<Record<string, ApiErrorCode | undefined>>({})
  const [allowance, setAllowance] = useState<Me | null>(null)
  const [allowanceTick, setAllowanceTick] = useState(0)
  const refreshAllowance = useCallback(() => setAllowanceTick((n) => n + 1), [])

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l)
    document.documentElement.lang = l
    document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr'
    document.cookie = `locale=${l}; path=/; max-age=31536000; samesite=lax`
    router.refresh() // Clerk's screens take their language from the server layout
  }, [router])

  /** Runs belong to a CV: once that CV is gone from the server, they are gone too. */
  const resetRuns = useCallback(() => {
    setRunId(null)
    setRun(null)
    setRunError(null)
    setSelected([])
    setBatches([])
    setTailorRuns({})
    setTailorErrors({})
  }, [])

  const markCvExpired = useCallback(() => {
    setCvState(null)
    setCvExpired(true)
    resetRuns()
  }, [resetRuns])

  // Restore after mount (the server render has no browser storage), once Clerk knows who is
  // signed in: the stored ids belong to one account. A change of account starts empty, and
  // signing out clears what was stored.
  const [owner, setOwner] = useState<string | null>(null)
  useEffect(() => {
    if (!isLoaded) return
    const current = userId ?? null
    if (owner !== null && current !== owner) clearSession()
    const saved = current ? loadSession(current) : emptySession
    setOwner(current)
    setCvState(saved.cv)
    setCvExpired(false)
    setSearch(saved.search)
    setRunId(saved.runId)
    setRun(null)
    setRunError(null)
    setSelected(saved.selected)
    setBatches(saved.batches)
    setTailorRuns({})
    setTailorErrors({})
    setAllowance(null)
    setHydrated(true)
    if (!saved.cv) return
    api.getCv(saved.cv.id).catch((e: unknown) => {
      if (errorCode(e) === 'expired') markCvExpired()
    })
    // `owner` is read only to notice a change of account, not to re-run on it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, userId, markCvExpired])

  useEffect(() => {
    if (hydrated && owner) saveSession(owner, { cv, search, runId, selected, batches })
  }, [hydrated, owner, cv, search, runId, selected, batches])

  // ---------------- CV ----------------
  const setCv = useCallback(
    (next: CvFile) => {
      if (cv && cv.id !== next.id) {
        api.deleteCv(cv.id).catch(() => {}) // if this fails it still expires on its own
        resetRuns()
      }
      setCvState(next)
      setCvExpired(false)
    },
    [cv, resetRuns],
  )

  const removeCv = useCallback(async () => {
    if (cv) {
      try {
        await api.deleteCv(cv.id)
      } catch (e) {
        if (errorCode(e) !== 'expired') throw e
      }
    }
    setCvState(null)
    setCvExpired(false)
    resetRuns()
  }, [cv, resetRuns])

  /** Everything of this account on the server (from any device), then what this browser holds. */
  const deleteAllData = useCallback(async () => {
    await api.deleteMyData()
    setCvState(null)
    setCvExpired(false)
    resetRuns()
    setSearch(null)
  }, [resetRuns])

  // ---------------- search ----------------
  const startSearch = useCallback(
    async (params: SearchParams, options?: { forceRefresh?: boolean }) => {
      if (!cv) return
      try {
        const started = await api.startSearch({
          cv_id: cv.id,
          title: params.title,
          more_titles: params.moreTitles ?? [],
          country: params.country,
          cities: params.cities,
          remote: params.remote,
          max_results: params.count,
          force_refresh: options?.forceRefresh ?? false,
        })
        setSearch(params)
        setRun(null)
        setRunError(null)
        setSelected([])
        setRunId(started.run_id)
      } catch (e) {
        if (errorCode(e) === 'expired') markCvExpired()
        throw e
      }
    },
    [cv, markCvExpired],
  )

  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    poll(() => api.getRun(runId), (r) => isFinished(r.status), setRun, { signal: controller.signal }).catch((e: unknown) => {
      if (!controller.signal.aborted) setRunError(errorCode(e))
    })
    return () => controller.abort()
  }, [runId])

  const toggleSelected = useCallback((id: string) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  }, [])
  const clearSelected = useCallback(() => setSelected([]), [])

  // ---------------- tailoring ----------------
  /** A job tailored again replaces its earlier entry; other finished PDFs stay available. */
  const addBatch = useCallback((batch: TailorBatch) => {
    const ids = new Set(batch.jobs.map((j) => j.id))
    setBatches((all) => [
      ...all.map((b) => ({ ...b, jobs: b.jobs.filter((j) => !ids.has(j.id)) })).filter((b) => b.jobs.length > 0),
      batch,
    ])
  }, [])

  const startTailor = useCallback(
    async (jobIds: string[], extraInfo: string) => {
      if (!runId || !run) return
      const jobs = jobIds.flatMap((id) => {
        const job = run.jobs.find((r) => r.job.id === id)?.job
        return job ? [{ id: job.id, title: job.title, company: job.company }] : []
      })
      const started = await api.startTailor({ run_id: runId, job_ids: jobIds, user_extra_info: extraInfo })
      addBatch({ id: started.run_id, searchRunId: runId, jobs })
      setSelected([])
    },
    [runId, run, addBatch],
  )

  const retryJob = useCallback(
    async (item: TailorItem) => {
      const batch = batches.find((b) => b.id === item.batchId)
      if (!batch) return
      const started = await api.startTailor({ run_id: batch.searchRunId, job_ids: [item.job.id] })
      addBatch({ id: started.run_id, searchRunId: batch.searchRunId, jobs: [item.job] })
    },
    [batches, addBatch],
  )

  const batchKey = batches.map((b) => b.id).join(',')
  useEffect(() => {
    if (!batchKey) return
    const controller = new AbortController()
    for (const id of batchKey.split(',')) {
      poll(
        () => api.getTailor(id),
        (r) => isFinished(r.status),
        (r) => {
          setTailorRuns((all) => ({ ...all, [id]: r }))
          setTailorErrors((all) => (all[id] ? { ...all, [id]: undefined } : all))
        },
        { signal: controller.signal },
      ).catch((e: unknown) => {
        if (!controller.signal.aborted) setTailorErrors((all) => ({ ...all, [id]: errorCode(e) }))
      })
    }
    return () => controller.abort()
  }, [batchKey])

  const items = useMemo(() => tailorItems(batches, tailorRuns, tailorErrors), [batches, tailorRuns, tailorErrors])

  // ---------------- the free allowance ----------------
  // Asked again whenever a run changes state, since a finished or failed run can use or refund it.
  const runsKey = `${run?.run_id}:${run?.status}|${items.map((i) => i.status).join()}`
  const wantsAllowance = isSignedIn === true || APP_PAGES.test(pathname)
  useEffect(() => {
    if (!hydrated || !wantsAllowance) return
    let current = true
    api
      .me()
      .then((me) => {
        if (current) setAllowance(me)
      })
      .catch(() => {}) // the backend still enforces the limits; the display just waits
    return () => {
      current = false
    }
  }, [hydrated, wantsAllowance, runsKey, allowanceTick])
  useEffect(() => {
    if (isSignedIn === false && !APP_PAGES.test(pathname)) setAllowance(null)
  }, [isSignedIn, pathname])

  const value = useMemo<AppState>(
    () => ({
      locale,
      t: dictionaries[locale],
      setLocale,
      hydrated,
      cv,
      cvExpired,
      setCv,
      removeCv,
      deleteAllData,
      cvBusy,
      setCvBusy,
      search,
      run,
      runId,
      runError,
      startSearch,
      selected,
      toggleSelected,
      clearSelected,
      items,
      startTailor,
      retryJob,
      allowance,
      refreshAllowance,
    }),
    [locale, setLocale, hydrated, cv, cvExpired, setCv, removeCv, deleteAllData, cvBusy, search, run, runId, runError, startSearch, selected, toggleSelected, clearSelected, items, startTailor, retryJob, allowance, refreshAllowance],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useApp must be used inside AppStateProvider')
  return ctx
}
