'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Check, FileSearch, Loader2, RefreshCw, SearchX, SlidersHorizontal, X } from 'lucide-react'
import { api, ApiError, isConnectionProblem, isFinished, type ApiErrorCode, type PricedEstimate } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import { formatDateTime, formatUsd } from '@/lib/format'
import { Button, buttonVariants } from '@/components/ui/button'
import { JobList } from './job-list'
import { JobDetail } from './job-detail'
import { ConfirmDialog } from './confirm-dialog'
import { cn } from '@/lib/utils'

function Panel({ icon, title, body, children, alert }: {
  icon: React.ReactNode
  title: string
  body?: string
  children?: React.ReactNode
  alert?: boolean
}) {
  return (
    <div role={alert ? 'alert' : 'status'} className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center px-4 py-20 text-center">
      <span className={cn('grid size-12 place-items-center rounded-full', alert ? 'bg-destructive/10 text-destructive' : 'bg-accent text-accent-foreground')}>
        {icon}
      </span>
      <h1 className="mt-4 text-2xl font-semibold">{title}</h1>
      {body && <p className="mt-2 text-muted-foreground">{body}</p>}
      {children}
    </div>
  )
}

const iconClass = 'size-6'

export function ResultsView() {
  const { t, hydrated, runId, run, runError, search, selected, clearSelected } = useApp()
  const params = useSearchParams()
  const [confirmOpen, setConfirmOpen] = useState(false)

  const toSearch = (
    <Link href="/search" className={cn(buttonVariants({ size: 'lg' }), 'mt-8 h-11 px-5')}>
      {t.search.editSearch}
    </Link>
  )

  if (!hydrated) return <div className="flex-1" aria-busy="true" />

  if (!runId) {
    return (
      <Panel icon={<FileSearch aria-hidden="true" className={iconClass} />} title={t.results.noSearchTitle} body={t.results.noSearchBody}>
        <Link href="/search" className={cn(buttonVariants({ size: 'lg' }), 'mt-8 h-11 px-5')}>
          {t.results.goSearch}
        </Link>
      </Panel>
    )
  }

  if (isConnectionProblem(runError ?? undefined)) {
    return (
      <Panel alert icon={<AlertCircle aria-hidden="true" className={iconClass} />} title={t.search.runLostTitle} body={t.search.runLostBody}>
        <Button size="lg" className="mt-8 h-11 px-5" onClick={() => window.location.reload()}>
          {t.search.reload}
        </Button>
      </Panel>
    )
  }

  if (runError) {
    return (
      <Panel alert icon={<AlertCircle aria-hidden="true" className={iconClass} />} title={t.search.runFailed} body={t.errors[runError]}>
        {toSearch}
      </Panel>
    )
  }

  if (!run || !isFinished(run.status)) {
    return (
      <Panel icon={<Loader2 aria-hidden="true" className={cn(iconClass, 'animate-spin')} />} title={t.search.running} body={t.search.runningBody} />
    )
  }

  if (run.status !== 'done') {
    return (
      <Panel
        alert
        icon={<AlertCircle aria-hidden="true" className={iconClass} />}
        title={run.status === 'stopped_cost_cap' ? t.search.runStopped : t.search.runFailed}
      >
        {toSearch}
      </Panel>
    )
  }

  if (run.jobs.length === 0) {
    return (
      <Panel icon={<SearchX aria-hidden="true" className={iconClass} />} title={t.search.emptyTitle} body={t.search.emptyBody}>
        <ul className="mt-6 flex flex-col gap-2 text-start text-sm">
          {t.search.emptyTips.map((tip) => (
            <li key={tip} className="flex gap-2">
              <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
              {tip}
            </li>
          ))}
        </ul>
        {toSearch}
      </Panel>
    )
  }

  const requested = params.get('job')
  const active = run.jobs.find((r) => r.job.id === requested) ?? run.jobs[0]
  const showDetailOnMobile = Boolean(requested)

  return (
    <>
      <div className="mx-auto grid w-full max-w-7xl flex-1 lg:grid-cols-[420px_1fr]">
        <section
          aria-labelledby="results-title"
          className={cn(
            'flex min-w-0 flex-col gap-4 px-4 py-6 pb-28 sm:px-6 lg:sticky lg:top-14 lg:h-[calc(100dvh-3.5rem)] lg:overflow-y-auto lg:border-e',
            showDetailOnMobile && 'hidden lg:flex',
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 id="results-title" className="text-2xl font-semibold tracking-tight">
                {t.results.title}
              </h1>
              {search && <p className="mt-1 text-sm text-muted-foreground [overflow-wrap:anywhere]">{t.results.summary(run.jobs.length, [search.title, ...(search.moreTitles ?? [])].join(' / '))}</p>}
            </div>
            <Link href="/search" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'h-11 shrink-0 px-3')}>
              <SlidersHorizontal aria-hidden="true" />
              {t.search.editSearch}
            </Link>
          </div>
          <LastUpdated />
          <JobList jobs={run.jobs} activeId={active.job.id} />
        </section>

        <section aria-label={active.job.title} className={cn('min-w-0 px-4 py-6 pb-28 sm:px-6 lg:px-10 lg:py-8', !showDetailOnMobile && 'hidden lg:block')}>
          <JobDetail key={active.job.id} ranked={active} />
        </section>
      </div>

      {selected.length > 0 && (
        <div
          role="region"
          aria-label={t.results.selectedCount(selected.length)}
          className="fixed inset-x-0 bottom-0 z-30 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
        >
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
            <p className="text-sm font-medium" aria-live="polite">
              {t.results.selectedCount(selected.length)}
            </p>
            <Button variant="ghost" size="lg" className="h-11 px-3" onClick={clearSelected}>
              {t.results.clear}
            </Button>
            <Button size="lg" className="ms-auto h-11 px-4" onClick={() => setConfirmOpen(true)}>
              {t.results.review}
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog open={confirmOpen} onClose={() => setConfirmOpen(false)} />
    </>
  )
}

function LastUpdated() {
  const { t, locale, run, cv, search, startSearch } = useApp()
  const ref = useRef<HTMLDialogElement>(null)
  const [estimate, setEstimate] = useState<PricedEstimate | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiErrorCode | null>(null)

  useEffect(() => () => ref.current?.close(), [])

  if (!run?.last_updated) return null
  const canRefresh = Boolean(cv && search)

  function open() {
    if (!search) return
    setError(null)
    setEstimate(null)
    ref.current?.showModal()
    api
      .estimateSearch({ country: search.country, cities: search.cities, remote: search.remote, max_results: search.count })
      .then(setEstimate)
      .catch(() => {})
  }

  async function confirm() {
    if (!search) return
    setBusy(true)
    setError(null)
    try {
      await startSearch(search, { forceRefresh: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'server')
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <p className="text-xs text-muted-foreground">{t.results.lastUpdated(formatDateTime(run.last_updated, locale))}</p>
      {canRefresh && (
        <Button variant="ghost" size="lg" className="-me-2 h-11 px-2 text-sm" onClick={open}>
          <RefreshCw aria-hidden="true" />
          {t.results.refresh}
        </Button>
      )}
      <dialog
        ref={ref}
        aria-labelledby="refresh-title"
        className="m-auto w-[calc(100%-2rem)] max-w-md rounded-xl border bg-background p-0 text-foreground shadow-xl backdrop:bg-foreground/40"
      >
        <div className="flex items-start justify-between gap-4 p-5">
          <div>
            <h2 id="refresh-title" className="text-xl font-semibold">
              {t.results.refreshTitle}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{t.results.refreshBody}</p>
          </div>
          <Button variant="ghost" size="icon-lg" className="size-11 shrink-0" onClick={() => ref.current?.close()} aria-label={t.common.cancel}>
            <X aria-hidden="true" />
          </Button>
        </div>
        <dl className="flex justify-between gap-4 border-t p-5 text-sm">
          <dt className="text-muted-foreground">{t.search.priceLabel}</dt>
          <dd className="font-semibold">{estimate ? formatUsd(estimate.price_to_user_usd) : t.search.priceLoading}</dd>
        </dl>
        {error && (
          <p role="alert" className="px-5 pb-3 text-sm text-destructive">
            {t.errors[error]}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 border-t p-5 sm:flex-row sm:justify-end">
          <Button variant="outline" size="lg" className="h-11 px-4" onClick={() => ref.current?.close()}>
            {t.common.cancel}
          </Button>
          <Button size="lg" className="h-11 px-4" disabled={busy || !estimate} onClick={confirm}>
            {busy ? t.results.refreshing : t.results.refreshConfirm}
          </Button>
        </div>
      </dialog>
    </div>
  )
}
