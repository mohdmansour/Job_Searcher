'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api, ApiError, type ApiErrorCode, type PricedEstimate } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import { formatUsd } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export function ConfirmDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, run, selected, toggleSelected, allowance, startTailor } = useApp()
  const router = useRouter()
  const ref = useRef<HTMLDialogElement>(null)
  const [estimate, setEstimate] = useState<PricedEstimate | null>(null)
  const [extra, setExtra] = useState('') // personal data: held only while the dialog is open
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiErrorCode | null>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  const count = selected.length
  useEffect(() => {
    setEstimate(null)
    if (!open || count === 0) return
    let current = true
    api
      .estimateTailor(count)
      .then((e) => {
        if (current) setEstimate(e)
      })
      .catch(() => {})
    return () => {
      current = false
    }
  }, [open, count])

  const overCap = estimate !== null && !estimate.within_cap
  // Free accounts see their allowance; owner accounts see the price in dollars.
  const free = allowance !== null && !allowance.unlimited
  const left = allowance?.free_tailors_left ?? 0
  const tooMany = free && count > left

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await startTailor(selected, extra.trim())
      setExtra('')
      onClose()
      router.push('/generate')
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="confirm-title"
      className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg overflow-hidden rounded-xl border bg-background p-0 text-foreground shadow-xl backdrop:bg-foreground/40 open:flex open:flex-col"
    >
      <div className="flex items-start justify-between gap-4 border-b p-5">
        <div>
          <h2 id="confirm-title" className="text-xl font-semibold">
            {t.results.confirmTitle}
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{t.results.confirmBody}</p>
        </div>
        <Button variant="ghost" size="icon-lg" className="size-11 shrink-0" onClick={onClose} aria-label={t.common.cancel}>
          <X aria-hidden="true" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {count === 0 ? (
          <p className="text-sm text-muted-foreground">{t.results.nothingSelected}</p>
        ) : (
          <ul className="flex flex-col divide-y rounded-lg border">
            {selected.map((id) => {
              const ranked = run?.jobs.find((r) => r.job.id === id)
              if (!ranked) return null
              const { job, match } = ranked
              return (
                <li key={id} className="flex items-center gap-3 px-4 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      <bdi>{job.title}</bdi>
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      <bdi>{job.company}</bdi>
                      {match && ` · ${match.score}%`}
                    </p>
                  </div>
                  <Button variant="ghost" size="icon" className="size-11 shrink-0" aria-label={t.results.removeJob(job.title)} onClick={() => toggleSelected(id)}>
                    <X aria-hidden="true" />
                  </Button>
                </li>
              )
            })}
          </ul>
        )}

        <div className="mt-5 flex flex-col gap-2">
          <Label htmlFor="extra-info">{t.results.extraLabel}</Label>
          <Textarea id="extra-info" value={extra} onChange={(e) => setExtra(e.target.value)} maxLength={5000} rows={3} dir="auto" className="bg-card text-base" />
          <p className="text-xs leading-relaxed text-muted-foreground">{t.results.extraHint}</p>
        </div>

        {free ? (
          <div className="mt-5 flex flex-col gap-2 text-sm" data-testid="tailor-allowance">
            <p className="font-medium">{t.allowance.cvsLeft(left)}</p>
            {tooMany ? (
              <p role="alert" className="text-destructive">
                {left === 0 ? t.allowance.used : t.allowance.tooMany(left)}
              </p>
            ) : (
              count > 0 && <p className="text-muted-foreground">{t.allowance.cvsUse(count)}</p>
            )}
          </div>
        ) : (
          <>
            <dl className="mt-5 flex justify-between gap-4 text-sm">
              <dt className="font-medium">{t.search.priceLabel}</dt>
              <dd className="font-semibold" data-testid="tailor-price">
                {count === 0 ? '—' : estimate ? formatUsd(estimate.price_to_user_usd) : t.search.priceLoading}
              </dd>
            </dl>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t.search.priceNote}</p>
          </>
        )}

        {overCap && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {t.results.overCap}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {t.errors[error]}
          </p>
        )}
      </div>

      <div className="flex flex-col-reverse gap-2 border-t p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:flex-row sm:justify-end">
        <Button variant="outline" size="lg" className="h-11 px-4" onClick={onClose}>
          {t.common.cancel}
        </Button>
        <Button size="lg" className="h-11 px-4" disabled={count === 0 || !estimate || overCap || tooMany || busy} onClick={confirm}>
          {t.results.confirm}
        </Button>
      </div>
    </dialog>
  )
}
