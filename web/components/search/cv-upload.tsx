'use client'

import { useId, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, FileText, Info, Loader2, UploadCloud } from 'lucide-react'
import { api, ApiError, type ApiErrorCode } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import { FileName } from '@/components/chrome'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Phase = 'idle' | 'uploading' | 'reading'
type UploadError = 'type' | ApiErrorCode

export const MAX_CV_BYTES = 10 * 1024 * 1024

export function CvUpload({ showError }: { showError?: boolean }) {
  const { t, cv, cvExpired, setCv, removeCv, setCvBusy } = useApp()
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<UploadError | null>(null)
  const [dragging, setDragging] = useState(false)
  const [pendingName, setPendingName] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const hintId = useId()
  const errorId = useId()

  async function handleFile(file: File | undefined) {
    if (!file || phase !== 'idle') return // one upload at a time
    setError(null)
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    if (!isPdf) return setError('type')
    if (file.size > MAX_CV_BYTES) return setError('too_large')
    setPendingName(file.name)
    setPhase('uploading')
    setCvBusy(true)
    try {
      const info = await api.uploadCv(file, () => setPhase('reading'))
      setCv({
        id: info.cv_id,
        name: file.name,
        sizeKb: Math.max(1, Math.round(file.size / 1024)),
        language: info.language,
        extraction: info.extraction,
      })
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'server')
    } finally {
      setPhase('idle')
      setCvBusy(false)
    }
  }

  async function remove() {
    setError(null)
    try {
      await removeCv()
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'server')
    }
  }

  const errorText =
    error === 'type' ? t.search.errType : error === 'rejected' ? t.search.errParse : error ? t.errors[error] : ''

  const fileInput = (
    <input
      ref={inputRef}
      type="file"
      accept="application/pdf,.pdf"
      className="sr-only"
      tabIndex={-1}
      aria-hidden="true"
      onChange={(e) => {
        handleFile(e.target.files?.[0])
        e.target.value = ''
      }}
    />
  )

  const errorBlock = error && (
    <div id={errorId} role="alert" className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
      <AlertCircle aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-destructive" />
      <div>
        <p className="font-medium text-destructive">{t.search.errTitle}</p>
        <p className="mt-1 text-sm">{errorText}</p>
      </div>
    </div>
  )

  if (cv && phase === 'idle') {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:p-5">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
              <FileText aria-hidden="true" className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium">
                <FileName name={cv.name} />
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-1 font-medium text-primary">
                  <CheckCircle2 aria-hidden="true" className="size-4" />
                  {t.search.ready}
                </span>
                <span aria-hidden="true">·</span>
                <span dir="ltr">{cv.sizeKb} KB</span>
                <span aria-hidden="true">·</span>
                {t.search.detected(t.common.langNames[cv.language])}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="lg" onClick={() => inputRef.current?.click()}>
              {t.search.replace}
            </Button>
            <Button variant="ghost" size="lg" onClick={remove}>
              {t.search.remove}
            </Button>
          </div>
          {fileInput}
        </div>
        {cv.extraction === 'ocr' && (
          <p className="flex gap-2 text-sm text-muted-foreground">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {t.search.ocrNote}
          </p>
        )}
        {errorBlock}
      </div>
    )
  }

  const busy = phase !== 'idle'

  return (
    <div className="flex flex-col gap-3">
      {cvExpired && !busy && (
        <p role="status" className="rounded-md bg-gap px-3 py-2 text-sm text-gap-foreground">
          {t.search.cvExpired}
        </p>
      )}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFile(e.dataTransfer.files?.[0])
        }}
        className={cn(
          'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed bg-card px-6 py-10 text-center transition-colors',
          dragging && 'border-primary bg-accent/50',
          error && 'border-destructive/50',
          showError && !busy && !error && 'border-destructive/50',
        )}
      >
        {busy ? (
          <div role="status" className="flex flex-col items-center gap-3">
            <Loader2 aria-hidden="true" className="size-8 animate-spin text-primary" />
            <p className="max-w-full truncate font-medium">
              <FileName name={pendingName} />
            </p>
            <p className="text-sm text-muted-foreground">{phase === 'uploading' ? t.search.uploading : t.search.reading}</p>
            <div aria-hidden="true" className="h-1.5 w-48 overflow-hidden rounded-full bg-muted">
              <div
                className={cn('h-full rounded-full bg-primary transition-all duration-700', phase === 'uploading' ? 'w-1/2' : 'w-11/12')}
              />
            </div>
          </div>
        ) : (
          <>
            <span className="grid size-12 place-items-center rounded-full bg-accent text-accent-foreground">
              <UploadCloud aria-hidden="true" className="size-6" />
            </span>
            <div>
              <p className="font-semibold">{t.search.dropTitle}</p>
              <p id={hintId} className="mt-1 text-sm text-muted-foreground">
                {t.search.dropHint}
              </p>
            </div>
            <Button
              size="lg"
              className="h-11 px-5"
              aria-describedby={error ? `${hintId} ${errorId}` : hintId}
              onClick={() => inputRef.current?.click()}
            >
              {t.search.browse}
            </Button>
          </>
        )}
        {fileInput}
      </div>
      {errorBlock}
      {showError && !error && !busy && (
        <p role="alert" className="text-sm text-destructive">
          {t.search.cvError}
        </p>
      )}
    </div>
  )
}
