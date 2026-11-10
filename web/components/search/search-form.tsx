'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Check, Loader2, Plus, X } from 'lucide-react'
import { api, ApiError, type ApiErrorCode, type PricedEstimate } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import { citySuggestions, countries } from '@/lib/countries'
import { formatUsd } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CvUpload } from './cv-upload'
import { cn } from '@/lib/utils'

const COUNTS = [10, 25, 50]
const MAX_CITIES = 10
const MAX_MORE_TITLES = 2

function addUnique(list: string[], value: string, max: number): string[] {
  const item = value.trim()
  if (!item || list.length >= max || list.some((x) => x.toLowerCase() === item.toLowerCase())) return list
  return [...list, item]
}

function TagInput({ values, onChange, max, label, placeholder, maxMessage, display = (v) => v }: {
  values: string[]
  onChange: (next: string[]) => void
  max: number
  label: string
  placeholder: string
  maxMessage: string
  display?: (value: string) => string
}) {
  const { t } = useApp()
  const [text, setText] = useState('')
  const full = values.length >= max
  function add() {
    onChange(addUnique(values, text, max))
    setText('')
  }
  return (
    <>
      <div className="flex gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder={placeholder}
          aria-label={label}
          disabled={full}
          maxLength={200}
          dir="auto"
          className="h-11 min-w-0 flex-1 bg-card text-base"
        />
        <Button type="button" variant="outline" size="lg" className="h-11 shrink-0 px-4" disabled={full || !text.trim()} onClick={add}>
          <Plus aria-hidden="true" />
          {t.search.citiesAdd}
        </Button>
      </div>
      {full && <p className="text-sm text-muted-foreground">{maxMessage}</p>}
      {values.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {values.map((value) => (
            <li key={value} className="inline-flex h-11 max-w-full items-center gap-1 rounded-full border border-primary bg-accent ps-4 text-sm font-medium text-accent-foreground">
              <bdi className="truncate">{display(value)}</bdi>
              <button
                type="button"
                onClick={() => onChange(values.filter((x) => x !== value))}
                aria-label={t.search.citiesRemove(display(value))}
                className="grid size-11 shrink-0 place-items-center rounded-full hover:bg-background/60"
              >
                <X aria-hidden="true" className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export function SearchForm() {
  const { hydrated, search } = useApp()
  // Wait for stored values so the form starts from the user's last search.
  if (!hydrated) return <div className="min-h-96" aria-busy="true" />
  return <Form key={search?.title ?? ''} />
}

function Form() {
  const { t, locale, cv, cvBusy, allowance, startSearch, search } = useApp()
  const router = useRouter()
  const [title, setTitle] = useState(search?.title ?? '')
  const [country, setCountry] = useState(search?.country ?? '')
  const [cities, setCities] = useState<string[]>(search?.cities ?? [])
  const [moreTitles, setMoreTitles] = useState<string[]>(search?.moreTitles ?? [])
  const [remote, setRemote] = useState(search?.remote ?? false)
  const [count, setCount] = useState(search?.count ?? 25)
  const [submitted, setSubmitted] = useState(false)
  const [running, setRunning] = useState(false)
  const [startError, setStartError] = useState<ApiErrorCode | null>(null)
  const [estimate, setEstimate] = useState<PricedEstimate | null>(null)
  const [estimateState, setEstimateState] = useState<'idle' | 'loading' | 'failed'>('idle')

  const citiesKey = cities.join('|')
  useEffect(() => {
    setEstimate(null)
    if (!country) {
      setEstimateState('idle')
      return
    }
    setEstimateState('loading')
    let current = true
    const timer = setTimeout(() => {
      api
        .estimateSearch({ country, cities: citiesKey ? citiesKey.split('|') : [], remote, max_results: count })
        .then((e) => {
          if (!current) return
          setEstimate(e)
          setEstimateState('idle')
        })
        .catch(() => {
          if (current) setEstimateState('failed')
        })
    }, 250)
    return () => {
      current = false
      clearTimeout(timer)
    }
  }, [country, citiesKey, remote, count])

  // Free accounts see their allowance; owner accounts see the price in dollars.
  const free = allowance !== null && !allowance.unlimited
  const maxFree = allowance?.free_max_results ?? Infinity
  const allowanceUsed = free && allowance.free_searches_left === 0
  useEffect(() => {
    if (free && count > maxFree) setCount(Math.max(...COUNTS.filter((n) => n <= maxFree)))
  }, [free, count, maxFree])

  const overCap = estimate !== null && !estimate.within_cap
  const priceMissing = Boolean(country) && estimate === null // the price always comes first
  const titleInvalid = submitted && !title.trim()
  const countryInvalid = submitted && !country
  const cvMissing = submitted && !cv
  const atCityLimit = cities.length >= MAX_CITIES

  const addCity = (name: string) => setCities((c) => addUnique(c, name, MAX_CITIES))

  const suggestions = citySuggestions[country] ?? []
  const cityLabel = (city: string) =>
    (locale === 'ar' && suggestions.find((s) => s.en.toLowerCase() === city.toLowerCase())?.ar) || city

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitted(true)
    setStartError(null)
    if (!title.trim() || !country || !cv || overCap || priceMissing || cvBusy || allowanceUsed) return
    setRunning(true)
    try {
      await startSearch({ title: title.trim(), moreTitles, country, cities, remote, count })
      router.push('/results')
    } catch (err) {
      setStartError(err instanceof ApiError ? err.code : 'server')
      setRunning(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-8 lg:grid-cols-[1fr_340px] lg:items-start">
      <div className="flex min-w-0 flex-col gap-10">
        <section aria-labelledby="cv-heading">
          <h2 id="cv-heading" className="mb-4 text-lg font-semibold">
            {t.search.cvSection}
          </h2>
          <CvUpload showError={cvMissing} />
        </section>

        <section aria-labelledby="job-heading" className="flex flex-col gap-6">
          <h2 id="job-heading" className="text-lg font-semibold">
            {t.search.jobSection}
          </h2>

          <div className="grid gap-6 sm:grid-cols-2">
            <div className="flex min-w-0 flex-col gap-2">
              <Label htmlFor="job-title">{t.search.jobTitle}</Label>
              <Input
                id="job-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t.search.jobTitlePh}
                maxLength={200}
                aria-invalid={titleInvalid || undefined}
                aria-describedby={titleInvalid ? 'title-error' : undefined}
                dir="auto"
                className="h-11 bg-card text-base"
                required
              />
              {titleInvalid && (
                <p id="title-error" className="text-sm text-destructive">
                  {t.search.titleError}
                </p>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-2">
              <Label htmlFor="country">
                {t.search.country} <span aria-hidden="true" className="text-destructive">*</span>
              </Label>
              <select
                id="country"
                value={country}
                onChange={(e) => {
                  setCountry(e.target.value)
                  setCities([])
                }}
                required
                aria-invalid={countryInvalid || undefined}
                aria-describedby="country-hint"
                className="h-11 w-full rounded-lg border border-input bg-card px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive"
              >
                <option value="">{t.search.countryPh}</option>
                {countries.map((c) => (
                  <option key={c.value} value={c.value}>
                    {locale === 'ar' ? c.ar : c.value}
                  </option>
                ))}
              </select>
              <p id="country-hint" className={cn('text-sm text-muted-foreground', countryInvalid && 'text-destructive')}>
                {countryInvalid ? t.search.countryError : t.search.countryHint}
              </p>
            </div>
          </div>

          <fieldset className="flex min-w-0 flex-col gap-3">
            <legend className="text-sm font-medium">{t.search.moreTitles}</legend>
            <p className="-mt-1 text-sm text-muted-foreground">{t.search.moreTitlesHint}</p>
            <TagInput
              values={moreTitles}
              onChange={setMoreTitles}
              max={MAX_MORE_TITLES}
              label={t.search.moreTitles}
              placeholder={t.search.moreTitlesPh}
              maxMessage={t.search.moreTitlesMax}
            />
          </fieldset>

          <fieldset className="flex min-w-0 flex-col gap-3">
            <legend className="text-sm font-medium">{t.search.cities}</legend>
            <p className="-mt-1 text-sm text-muted-foreground">{t.search.citiesHint}</p>
            <TagInput
              values={cities}
              onChange={setCities}
              max={MAX_CITIES}
              label={t.search.cities}
              placeholder={t.search.citiesPh}
              maxMessage={t.search.citiesMax}
              display={cityLabel}
            />
            {suggestions.some((s) => !cities.includes(s.en)) && (
              <div className="flex flex-wrap gap-2">
                {suggestions
                  .filter((s) => !cities.includes(s.en))
                  .map((s) => (
                    <button
                      key={s.en}
                      type="button"
                      disabled={atCityLimit}
                      onClick={() => addCity(s.en)}
                      className="inline-flex h-11 items-center gap-1.5 rounded-full border bg-card px-4 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
                    >
                      <Plus aria-hidden="true" className="size-4" />
                      {locale === 'ar' ? s.ar : s.en}
                    </button>
                  ))}
              </div>
            )}
          </fieldset>

          <label className="flex cursor-pointer items-start gap-3 rounded-lg border bg-card p-4">
            <Checkbox checked={remote} onCheckedChange={(v) => setRemote(Boolean(v))} className="mt-0.5 size-5" />
            <span>
              <span className="block text-sm font-medium">{t.search.remote}</span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{t.search.remoteHint}</span>
            </span>
          </label>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-sm font-medium">{t.search.count}</legend>
            <div className="grid max-w-sm grid-cols-3 gap-2">
              {COUNTS.map((n) => (
                <label
                  key={n}
                  className="flex h-11 cursor-pointer items-center justify-center rounded-lg border bg-card text-sm font-medium has-[:checked]:border-primary has-[:checked]:bg-accent has-[:checked]:text-accent-foreground has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50"
                >
                  <input type="radio" name="count" value={n} checked={count === n} disabled={free && n > maxFree} onChange={() => setCount(n)} className="sr-only" />
                  {n}
                </label>
              ))}
            </div>
            {free && <p className="text-sm text-muted-foreground">{t.allowance.freeMax(maxFree)}</p>}
          </fieldset>
        </section>
      </div>

      <aside className="rounded-xl border bg-card p-5 lg:sticky lg:top-24" aria-labelledby="cost-heading">
        <h2 id="cost-heading" className="font-semibold">
          {t.search.costTitle}
        </h2>
        {free ? (
          <div className="mt-4 flex flex-col gap-2 text-sm" data-testid="search-allowance">
            <p className="font-medium">{t.allowance.searchesLeft(allowance.free_searches_left)}</p>
            <p className="text-muted-foreground">{allowanceUsed ? t.allowance.used : t.allowance.searchUses}</p>
          </div>
        ) : (
          <>
        <dl className="mt-4 flex flex-col gap-3 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{t.search.priceLabel}</dt>
            <dd className="font-semibold" data-testid="search-price" aria-live="polite">
              {estimate
                ? formatUsd(estimate.price_to_user_usd)
                : estimateState === 'loading'
                  ? t.search.priceLoading
                  : estimateState === 'failed'
                    ? t.search.priceUnavailable
                    : '—'}
            </dd>
          </div>
        </dl>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t.search.priceNote}</p>
        {allowance?.unlimited && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t.allowance.ownerNote}</p>}
          </>
        )}

        {overCap && (
          <p role="alert" className="mt-4 text-sm text-destructive">
            {t.search.overCap}
          </p>
        )}
        {startError && (
          <p role="alert" className="mt-4 text-sm text-destructive">
            {t.errors[startError]}
          </p>
        )}
        <Button type="submit" size="lg" className="mt-5 h-11 w-full text-base" disabled={running || overCap || priceMissing || cvBusy || allowanceUsed}>
          {running ? (
            <>
              <Loader2 aria-hidden="true" className="animate-spin" />
              {t.search.running}
            </>
          ) : (
            t.search.start
          )}
        </Button>
      </aside>
    </form>
  )
}

export function SearchPageHeader() {
  const { t } = useApp()
  return (
    <div className="mb-8 max-w-2xl">
      <h1 className="text-3xl font-semibold tracking-tight">{t.search.title}</h1>
      <p className="mt-2 leading-relaxed text-muted-foreground">{t.search.body}</p>
    </div>
  )
}
