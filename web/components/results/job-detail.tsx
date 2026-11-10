'use client'

import Link from 'next/link'
import { AlertCircle, ArrowLeft, Check, ExternalLink, Info, MapPin, Plus } from 'lucide-react'
import type { RankedJob } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import { daysAgo } from '@/lib/format'
import { Button, buttonVariants } from '@/components/ui/button'
import { ScoreBadge } from '@/components/chrome'
import { GapList, ReasonList, SkillChips } from './match-breakdown'
import { cn } from '@/lib/utils'

const isWebLink = (url: string) => /^https?:\/\//i.test(url)

export function JobDetail({ ranked }: { ranked: RankedJob }) {
  const { t, selected, toggleSelected } = useApp()
  const { job, match } = ranked
  const isSelected = selected.includes(job.id)
  const age = job.posted_at ? daysAgo(job.posted_at) : null

  return (
    <article aria-labelledby="job-detail-title" className="flex flex-col gap-8">
      <Link href="/results" className={cn(buttonVariants({ variant: 'ghost', size: 'lg' }), '-ms-3 h-11 self-start px-3 lg:hidden')}>
        <ArrowLeft aria-hidden="true" className="rtl:rotate-180" />
        {t.results.backToList}
      </Link>

      <header className="flex flex-col gap-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 id="job-detail-title" className="text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">
              <bdi>{job.title}</bdi>
            </h2>
            <p className="mt-1 text-lg text-foreground/80 [overflow-wrap:anywhere]">
              <bdi>{job.company}</bdi>
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              <MapPin aria-hidden="true" className="size-4 shrink-0" />
              <bdi className="[overflow-wrap:anywhere]">{job.location}</bdi>
              {job.remote && (
                <>
                  <span aria-hidden="true">·</span>
                  {t.results.remoteTag}
                </>
              )}
              {age !== null && (
                <>
                  <span aria-hidden="true">·</span>
                  {age === 0 ? t.results.postedToday : t.results.posted(age)}
                </>
              )}
            </p>
          </div>
          {match && (
            <div className="w-full shrink-0 rounded-lg border bg-card p-4 sm:w-48">
              <p className="text-sm font-medium text-muted-foreground">{t.results.matchEstimate}</p>
              <div className="mt-1">
                <ScoreBadge score={match.score} size="lg" />
              </div>
            </div>
          )}
        </div>
        {match ? (
          <p className="flex gap-2 text-sm text-muted-foreground">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {t.results.scoreExplain}
          </p>
        ) : (
          <p role="status" className="flex gap-2 rounded-md bg-gap px-3 py-2 text-sm text-gap-foreground">
            <AlertCircle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {t.results.scoreFailed}
          </p>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            size="lg"
            variant={isSelected ? 'secondary' : 'default'}
            aria-pressed={isSelected}
            onClick={() => toggleSelected(job.id)}
            className="h-11 px-4"
          >
            {isSelected ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
            {isSelected ? t.results.removeFromSelection : t.results.addToSelection}
          </Button>
          {isWebLink(job.url) && (
            <a href={job.url} target="_blank" rel="noopener noreferrer" className={cn(buttonVariants({ variant: 'outline', size: 'lg' }), 'h-11 px-4')}>
              {t.results.viewOriginal}
              <ExternalLink aria-hidden="true" />
            </a>
          )}
        </div>
      </header>

      {match && (
        <>
          <section aria-labelledby="matches-h" className="rounded-xl border bg-card p-5">
            <h3 id="matches-h" className="text-lg font-semibold">
              {t.results.whatMatches}
            </h3>
            <p className="mb-5 mt-1 text-sm text-muted-foreground">{t.results.whatMatchesBody}</p>
            <ReasonList reasons={match.reasons} />
            {match.matched_skills.length > 0 && (
              <div className="mt-5 border-t pt-4">
                <h4 className="mb-3 text-sm font-semibold">{t.results.skillsTitle}</h4>
                <SkillChips skills={match.matched_skills} />
              </div>
            )}
          </section>

          <section aria-labelledby="gaps-h" className="rounded-xl border border-gap-foreground/20 bg-gap/40 p-5">
            <h3 id="gaps-h" className="text-lg font-semibold">
              {t.results.whatsMissing} <span className="text-muted-foreground tabular-nums">({match.gaps.length})</span>
            </h3>
            {match.gaps.length > 0 ? (
              <>
                <p className="mb-5 mt-1 text-sm text-muted-foreground">{t.results.whatsMissingBody}</p>
                <GapList gaps={match.gaps} />
                <p className="mt-5 border-t border-gap-foreground/15 pt-4 text-sm">{t.results.gapAdvice}</p>
              </>
            ) : (
              <p className="mt-1 text-sm text-muted-foreground">{t.results.noGaps}</p>
            )}
          </section>
        </>
      )}

      <section aria-labelledby="desc-h">
        <h3 id="desc-h" className="text-lg font-semibold">
          {t.results.description}
        </h3>
        <p dir="auto" className="mt-4 whitespace-pre-line leading-relaxed text-foreground/85 [overflow-wrap:anywhere]">
          {job.description}
        </p>
      </section>
    </article>
  )
}
