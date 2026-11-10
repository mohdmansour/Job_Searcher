'use client'

import Link from 'next/link'
import { useState } from 'react'
import { AlertTriangle, Check, Download, FileText, Loader2, RotateCcw } from 'lucide-react'
import { ApiError, isConnectionProblem, pdfHref, refreshSession, type ApiErrorCode, type TailoredJob } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import type { ItemStatus, TailorItem } from '@/lib/tailor-state'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Which of the three stages (waiting, working, ready) each status has reached. */
const STAGE_INDEX: Record<ItemStatus, number> = { waiting: 0, working: 1, done: 2, failed: 1, stopped: 1, expired: 1, error: 1 }
const PROBLEM: ItemStatus[] = ['failed', 'stopped', 'expired', 'error']

export function GenerateView() {
  const { t, hydrated, items } = useApp()

  if (!hydrated) return <div className="flex-1" aria-busy="true" />

  if (items.length === 0) {
    return (
      <div className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center px-4 py-20 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-accent text-accent-foreground">
          <FileText aria-hidden="true" className="size-6" />
        </span>
        <h1 className="mt-4 text-2xl font-semibold">{t.generate.noneTitle}</h1>
        <p className="mt-2 text-muted-foreground">{t.generate.noneBody}</p>
        <Link href="/results" className={cn(buttonVariants({ size: 'lg' }), 'mt-8 h-11 px-5')}>
          {t.generate.toResults}
        </Link>
      </div>
    )
  }

  const done = items.filter((i) => i.status === 'done').length

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 md:py-12">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t.generate.title}</h1>
          <p className="mt-2 max-w-xl leading-relaxed text-muted-foreground">{t.generate.body}</p>
        </div>
        <p className="shrink-0 text-sm font-medium" aria-live="polite">
          {t.generate.complete(done, items.length)}
        </p>
      </div>
      <ul className="mt-8 flex flex-col gap-4">
        {items.map((item) => (
          <GenCard key={`${item.batchId}:${item.job.id}`} item={item} />
        ))}
      </ul>
      <div className="mt-8 flex flex-col gap-2 sm:flex-row">
        <Link href="/results" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'h-11 px-4')}>
          {t.generate.toResults}
        </Link>
        <Link href="/search" className={cn(buttonVariants({ variant: 'ghost', size: 'lg' }), 'h-11 px-4')}>
          {t.generate.newSearch}
        </Link>
      </div>
    </div>
  )
}

/** A page left open can hold an expired session, so renew it before starting the download. */
async function downloadPdf(event: React.MouseEvent<HTMLAnchorElement>) {
  event.preventDefault()
  const href = event.currentTarget.href
  await refreshSession()
  const link = document.createElement('a')
  link.href = href
  link.download = ''
  link.click()
}

function GenCard({ item }: { item: TailorItem }) {
  const { t, retryJob } = useApp()
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState<ApiErrorCode | null>(null)
  const { job, status, result } = item
  const current = STAGE_INDEX[status]
  const hasProblem = PROBLEM.includes(status)
  const connectionLost = status === 'error' && isConnectionProblem(item.errorCode)
  const canRetry = hasProblem && status !== 'expired' && !connectionLost // it may still be running

  async function retry() {
    setRetrying(true)
    setRetryError(null)
    try {
      await retryJob(item)
    } catch (e) {
      setRetryError(e instanceof ApiError ? e.code : 'server')
      setRetrying(false)
    }
  }

  const problemTitle = status === 'expired' ? t.generate.expiredTitle : connectionLost ? t.search.runLostTitle : t.generate.failed
  const problemBody =
    status === 'expired'
      ? t.generate.expiredBody
      : connectionLost
        ? t.search.runLostBody
      : status === 'stopped'
        ? t.generate.stoppedBody
        : status === 'error' && item.errorCode
          ? t.errors[item.errorCode]
          : t.generate.failedBody

  return (
    <li className={cn('rounded-xl border bg-card p-5', hasProblem && 'border-destructive/30')}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="font-semibold [overflow-wrap:anywhere]">
            <bdi>{job.title}</bdi>
          </h2>
          <p className="text-sm text-muted-foreground [overflow-wrap:anywhere]">
            <bdi>{job.company}</bdi>
          </p>
        </div>
        {result && (
          <a href={pdfHref(result.pdf_url)} download onClick={downloadPdf} className={cn(buttonVariants({ size: 'lg' }), 'h-11 shrink-0 px-4')}>
            <Download aria-hidden="true" />
            {t.generate.download}
          </a>
        )}
        {canRetry && (
          <Button variant="outline" size="lg" className="h-11 shrink-0 px-4" disabled={retrying} onClick={retry}>
            <RotateCcw aria-hidden="true" />
            {t.generate.retry}
          </Button>
        )}
      </div>

      <ol aria-label={t.generate.progressLabel(job.title)} className="mt-5 grid gap-2 sm:grid-cols-3">
        {t.generate.stages.map((label, i) => {
          const complete = i < current || (status === 'done' && i === 2)
          const active = i === current && (status === 'waiting' || status === 'working')
          const errored = hasProblem && i === current
          return (
            <li
              key={label}
              aria-current={active ? 'step' : undefined}
              className={cn(
                'flex items-center gap-2 rounded-md border px-3 py-2 text-sm',
                complete && 'border-primary/30 bg-accent/60 text-accent-foreground',
                active && 'border-primary font-medium',
                errored && 'border-destructive/40 bg-destructive/5 text-destructive',
                !complete && !active && !errored && 'text-muted-foreground',
              )}
            >
              {complete ? (
                <Check aria-hidden="true" className="size-4 shrink-0" />
              ) : active ? (
                <Loader2 aria-hidden="true" className="size-4 shrink-0 animate-spin" />
              ) : errored ? (
                <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
              ) : (
                <span aria-hidden="true" className="size-4 shrink-0 rounded-full border" />
              )}
              {label}
            </li>
          )
        })}
      </ol>

      {hasProblem && (
        <div role="alert" className="mt-4 rounded-md bg-destructive/5 p-3 text-sm">
          <p className="font-medium text-destructive">{problemTitle}</p>
          <p className="mt-1">{problemBody}</p>
        </div>
      )}
      {retryError && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {t.errors[retryError]}
        </p>
      )}

      {result && <ResultDetails result={result} />}
    </li>
  )
}

function ResultDetails({ result }: { result: TailoredJob }) {
  const { t, cv } = useApp()
  // A line that only moved has nothing to compare: list it once instead of before-and-after.
  const edits = result.change_log.filter((c) => c.kind !== 'moved')
  const moved = result.change_log.filter((c) => c.kind === 'moved')
  const suggestions = result.suggestions ?? []

  return (
    <>
      {result.warning && result.remaining_violations.length > 0 && (
        <div role="status" className="mt-4 rounded-md border border-gap-foreground/20 bg-gap/40 p-4 text-sm">
          <p className="flex items-center gap-2 font-semibold">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0 text-gap-foreground" />
            {t.generate.warningTitle}
          </p>
          <p className="mt-1">{t.generate.warningBody}</p>
          <ul className="mt-3 flex flex-col gap-3">
            {result.remaining_violations.map((v) => (
              <li key={v.adapted_text} className="border-t border-gap-foreground/15 pt-3">
                <p dir="auto" className="font-medium [overflow-wrap:anywhere]">{v.adapted_text}</p>
                <p dir="auto" className="mt-1 text-muted-foreground [overflow-wrap:anywhere]">{v.explanation}</p>
                {v.suggested_fix && (
                  <p dir="auto" className="mt-1 [overflow-wrap:anywhere]">
                    <span className="font-medium">{t.generate.warningFix}: </span>
                    {v.suggested_fix}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 border-t pt-4">
        <h3 className="text-sm font-semibold">{t.generate.changesTitle}</h3>
        {edits.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">{t.generate.noChanges}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-4 text-sm" data-testid="changes">
            {edits.map((c) => (
              <li key={`${c.original}|${c.adapted}`} className="flex flex-col gap-1.5">
                <span className="self-start rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {c.kind === 'fixed' ? t.generate.kindFixed : t.generate.kindReworded}
                </span>
                <p className="[overflow-wrap:anywhere]">
                  <span className="font-medium text-muted-foreground">{t.generate.changeOriginal}: </span>
                  <bdi>{c.original}</bdi>
                </p>
                <p className="[overflow-wrap:anywhere]">
                  <span className="font-medium">{t.generate.changeTailored}: </span>
                  <bdi>{c.adapted}</bdi>
                </p>
                <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
                  <span className="font-medium">{t.generate.changeWhy}: </span>
                  <bdi>{c.why_faithful}</bdi>
                </p>
              </li>
            ))}
          </ul>
        )}
        {moved.length > 0 && (
          <div className="mt-5" data-testid="moved">
            <h4 className="text-sm font-semibold">{t.generate.movedTitle}</h4>
            <ul className="mt-2 flex list-disc flex-col gap-1.5 ps-5 text-sm text-muted-foreground">
              {moved.map((c) => (
                <li key={c.original} className="[overflow-wrap:anywhere]">
                  <bdi>{c.adapted}</bdi>
                </li>
              ))}
            </ul>
          </div>
        )}
        {cv && <p className="mt-3 text-xs text-muted-foreground">{t.generate.languageSame(t.common.langNames[cv.language])}</p>}
      </div>

      {suggestions.length > 0 && (
        <div className="mt-5 rounded-lg border bg-muted/40 p-4" data-testid="suggestions">
          <h3 className="text-sm font-semibold">{t.generate.suggestionsTitle}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t.generate.suggestionsBody}</p>
          <ul className="mt-3 flex list-disc flex-col gap-1.5 ps-5 text-sm">
            {suggestions.map((s) => (
              <li key={s} dir="auto" className="[overflow-wrap:anywhere]">{s}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
