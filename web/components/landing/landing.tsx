'use client'

import Link from 'next/link'
import { ArrowRight, Ban, ChevronDown, FileSearch, FileText, ListChecks, MapPin } from 'lucide-react'
import { useApp } from '@/lib/app-state'
import { buttonVariants } from '@/components/ui/button'
import { ScoreBadge } from '@/components/chrome'
import { GapList, ReasonList } from '@/components/results/match-breakdown'
import { cn } from '@/lib/utils'

export function Hero() {
  const { t } = useApp()
  return (
    <section className="mx-auto grid max-w-6xl gap-12 px-4 pb-16 pt-12 sm:px-6 md:pt-20 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wider text-primary rtl:tracking-normal">{t.landing.eyebrow}</p>
        <h1 className="mt-4 text-balance text-4xl font-semibold leading-tight tracking-tight sm:text-5xl rtl:leading-snug">
          {t.landing.title}
        </h1>
        <p className="mt-6 max-w-xl text-pretty text-lg leading-relaxed text-muted-foreground">{t.landing.body}</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link href="/search" className={cn(buttonVariants({ size: 'lg' }), 'h-11 px-5 text-base')}>
            {t.landing.ctaPrimary}
            <ArrowRight aria-hidden="true" className="rtl:rotate-180" />
          </Link>
        </div>
        <p className="mt-5 text-sm text-muted-foreground">{t.landing.note}</p>
      </div>
      <MatchPreview />
    </section>
  )
}

function MatchPreview() {
  const { t } = useApp()
  const example = t.landing.example
  return (
    <figure aria-label={t.landing.previewTitle} className="rounded-xl border bg-card p-5 shadow-sm sm:p-6">
      <figcaption className="sr-only">{t.landing.previewTitle}</figcaption>
      <span className="rounded-full bg-gap px-2 py-0.5 text-[11px] font-medium text-gap-foreground">{example.tag}</span>
      <div className="mt-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-lg font-semibold">{example.title}</p>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
            <bdi>{example.company}</bdi>
            <span aria-hidden="true">·</span>
            <MapPin aria-hidden="true" className="size-3.5" />
            <bdi>{example.location}</bdi>
          </p>
        </div>
        <div className="text-end">
          <ScoreBadge score={82} />
          <p className="mt-1.5 text-xs text-muted-foreground">{t.landing.previewScore}</p>
        </div>
      </div>
      <div className="mt-6 grid gap-6">
        <div>
          <h3 className="mb-3 text-sm font-semibold">{t.results.whatMatches}</h3>
          <ReasonList reasons={example.reasons} />
        </div>
        <div className="border-t pt-5">
          <h3 className="mb-3 text-sm font-semibold">{t.results.whatsMissing}</h3>
          <GapList gaps={example.gaps} />
        </div>
      </div>
    </figure>
  )
}

export function Steps() {
  const { t } = useApp()
  const icons = [FileText, FileSearch, ListChecks]
  return (
    <section id="how" className="scroll-mt-20 border-y bg-card/60">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
        <h2 className="text-3xl font-semibold tracking-tight">{t.landing.stepsTitle}</h2>
        <p className="mt-3 text-muted-foreground">{t.landing.stepsBody}</p>
        <ol className="mt-10 grid gap-8 md:grid-cols-3">
          {t.landing.steps.map((s, i) => {
            const Icon = icons[i]
            return (
              <li key={s.title} className="flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <Icon aria-hidden="true" className="size-5" />
                  </span>
                  <span className="text-sm font-medium text-muted-foreground tabular-nums">0{i + 1}</span>
                </div>
                <h3 className="text-lg font-semibold">{s.title}</h3>
                <p className="leading-relaxed text-muted-foreground">{s.body}</p>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}

export function NeverAdd() {
  const { t } = useApp()
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
      <div className="grid gap-8 rounded-xl bg-foreground p-8 text-background md:grid-cols-2 md:p-12">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t.landing.neverTitle}</h2>
          <p className="mt-4 leading-relaxed text-background/75">{t.landing.neverBody}</p>
        </div>
        <ul className="grid gap-3 sm:grid-cols-2">
          {t.landing.never.map((n) => (
            <li key={n} className="flex items-center gap-3 rounded-lg border border-background/15 px-4 py-3">
              <Ban aria-hidden="true" className="size-4 shrink-0 text-background/60" />
              {n}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

export function PricingSummary() {
  const { t } = useApp()
  const rows = [
    { label: t.landing.pricingSearch, detail: t.landing.pricingSearchDetail, value: '1' },
    { label: t.landing.pricingCv, detail: t.landing.pricingCvDetail, value: '1' },
  ]
  return (
    <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6 md:pb-20">
      <div className="grid gap-10 md:grid-cols-[1fr_1.2fr] md:items-start">
        <div>
          <h2 className="text-3xl font-semibold tracking-tight">{t.landing.pricingTitle}</h2>
          <p className="mt-3 leading-relaxed text-muted-foreground">{t.landing.pricingBody}</p>
        </div>
        <div className="rounded-xl border bg-card">
          <dl className="divide-y">
            {rows.map((r) => (
              <div key={r.label} className="flex items-center justify-between gap-4 p-5">
                <div>
                  <dt className="font-medium">{r.label}</dt>
                  <dd className="mt-1 text-sm text-muted-foreground">{r.detail}</dd>
                </div>
                <dd className="shrink-0 text-2xl font-semibold tabular-nums" dir="ltr">
                  {r.value}
                </dd>
              </div>
            ))}
          </dl>
          <div className="border-t p-5">
            <Link href="/pricing" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'w-full sm:w-auto')}>
              {t.landing.pricingCta}
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

export function Faq() {
  const { t } = useApp()
  return (
    <section id="faq" className="scroll-mt-20 border-t bg-card/60">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 md:py-20">
        <h2 className="text-3xl font-semibold tracking-tight">{t.landing.faqTitle}</h2>
        <div className="mt-8 divide-y rounded-xl border bg-card">
          {t.landing.faqs.map((f) => (
            <details key={f.q} className="group p-5 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">
                {f.q}
                <ChevronDown aria-hidden="true" className="size-4 shrink-0 transition-transform group-open:rotate-180" />
              </summary>
              <p className="mt-3 leading-relaxed text-muted-foreground">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

export function FinalCta() {
  const { t } = useApp()
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 text-center sm:px-6 md:py-20">
      <h2 className="text-balance text-3xl font-semibold tracking-tight">{t.landing.finalTitle}</h2>
      <p className="mx-auto mt-3 max-w-lg text-muted-foreground">{t.landing.finalBody}</p>
      <Link href="/search" className={cn(buttonVariants({ size: 'lg' }), 'mt-8 h-11 px-5 text-base')}>
        {t.landing.ctaPrimary}
        <ArrowRight aria-hidden="true" className="rtl:rotate-180" />
      </Link>
    </section>
  )
}
