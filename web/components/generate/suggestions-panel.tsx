'use client'

import { useState } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import { ApiError, type ApiErrorCode, type Suggestion } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import type { TailorItem } from '@/lib/tailor-state'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'

/**
 * Suggestions the user can act on: tick the ones that are true (details optional), then make this
 * CV again with them. Ticked items are passed only in the request, never stored in the browser.
 * Tips (advice about the master CV) are listed without a tick box.
 */
export function SuggestionsPanel({ item, suggestions, redoAvailable }: {
  item: TailorItem
  suggestions: Suggestion[]
  redoAvailable: boolean
}) {
  const { t, redoJob } = useApp()
  const [picked, setPicked] = useState<Record<string, string>>({}) // label -> details
  const [busy, setBusy] = useState(false)
  const [started, setStarted] = useState(false)
  const [error, setError] = useState<ApiErrorCode | null>(null)
  const chosen = Object.keys(picked)

  const toggle = (label: string, on: boolean) =>
    setPicked((p) => {
      const next = { ...p }
      if (on) next[label] = next[label] ?? ''
      else delete next[label]
      return next
    })

  async function redo() {
    setBusy(true)
    setError(null)
    try {
      await redoJob(item, chosen.map((label) => ({ label, details: picked[label].trim() })))
      setPicked({})
      setStarted(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.code : 'server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-5 rounded-lg border bg-muted/40 p-4" data-testid="suggestions">
      <h3 className="text-sm font-semibold">{t.generate.suggestionsTitle}</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        {redoAvailable ? t.generate.suggestionsPick : t.generate.suggestionsBody}
      </p>
      <ul className="mt-3 flex flex-col gap-3 text-sm">
        {suggestions.map((s) =>
          s.kind === 'tip' || !redoAvailable ? (
            <li key={s.label} dir="auto" className="flex gap-2 [overflow-wrap:anywhere]">
              <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
              {s.text}
            </li>
          ) : (
            <li key={s.label} className="flex flex-col gap-2">
              <label className="flex cursor-pointer items-start gap-3">
                <Checkbox
                  checked={s.label in picked}
                  onCheckedChange={(v) => toggle(s.label, Boolean(v))}
                  className="mt-0.5 size-5"
                />
                <span dir="auto" className="[overflow-wrap:anywhere]">{s.text}</span>
              </label>
              {s.label in picked && (
                <Input
                  value={picked[s.label]}
                  onChange={(e) => setPicked((p) => ({ ...p, [s.label]: e.target.value }))}
                  maxLength={500}
                  dir="auto"
                  aria-label={t.generate.detailsLabel(s.label)}
                  placeholder={t.generate.detailsPlaceholder}
                  className="ms-8 h-11 w-auto bg-card text-base sm:text-sm"
                />
              )}
            </li>
          ),
        )}
      </ul>

      {chosen.length > 0 && (
        <div className="mt-4 flex flex-col gap-2 border-t pt-4">
          <p className="text-xs text-muted-foreground">{t.generate.redoHonesty}</p>
          <Button size="lg" className="h-11 self-start px-4" disabled={busy} onClick={redo}>
            {busy ? <Loader2 aria-hidden="true" className="animate-spin" /> : <RotateCcw aria-hidden="true" />}
            {t.generate.redo(chosen.length)}
          </Button>
        </div>
      )}
      {started && <p role="status" className="mt-3 text-sm">{t.generate.redoStarted}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-destructive">{t.errors[error]}</p>}
    </div>
  )
}
