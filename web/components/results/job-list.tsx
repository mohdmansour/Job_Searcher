'use client'

import Link from 'next/link'
import { MapPin } from 'lucide-react'
import type { RankedJob } from '@/lib/api'
import { useApp } from '@/lib/app-state'
import { Checkbox } from '@/components/ui/checkbox'
import { ScoreBadge } from '@/components/chrome'
import { cn } from '@/lib/utils'

export function JobList({ jobs, activeId }: { jobs: RankedJob[]; activeId?: string }) {
  const { t, selected, toggleSelected } = useApp()
  return (
    <ol aria-label={t.results.listLabel} className="flex flex-col gap-2">
      {jobs.map(({ job, match }, i) => {
        const isActive = job.id === activeId
        const isSelected = selected.includes(job.id)
        return (
          <li
            key={job.id}
            className={cn(
              'relative flex items-start gap-3 rounded-lg border bg-card p-4 transition-colors hover:border-foreground/20',
              isActive && 'lg:border-primary lg:ring-1 lg:ring-primary',
              isSelected && 'bg-accent/40',
            )}
          >
            <div className="relative z-10 pt-0.5">
              <Checkbox
                checked={isSelected}
                onCheckedChange={() => toggleSelected(job.id)}
                aria-label={t.results.selectFor(job.title, job.company)}
                className="size-5"
              />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-muted-foreground tabular-nums">{t.results.rank(i + 1)}</p>
              <h3 className="mt-0.5 font-semibold leading-snug [overflow-wrap:anywhere]">
                <Link
                  href={`/results?job=${encodeURIComponent(job.id)}`}
                  aria-current={isActive ? 'true' : undefined}
                  className="outline-none after:absolute after:inset-0 after:rounded-lg focus-visible:after:ring-3 focus-visible:after:ring-ring/50"
                >
                  <bdi>{job.title}</bdi>
                </Link>
              </h3>
              <p className="mt-1 text-sm text-foreground/80 [overflow-wrap:anywhere]">
                <bdi>{job.company}</bdi>
              </p>
              <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-muted-foreground">
                <MapPin aria-hidden="true" className="size-3.5 shrink-0" />
                <bdi className="[overflow-wrap:anywhere]">{job.location}</bdi>
                {job.remote && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium text-foreground/80">{t.results.remoteTag}</span>
                  </>
                )}
              </p>
            </div>
            <div className="shrink-0 text-end">
              {match ? (
                <>
                  <ScoreBadge score={match.score} />
                  <p className="mt-1.5 text-[11px] leading-tight text-muted-foreground">{t.results.matchEstimate}</p>
                </>
              ) : (
                <p className="text-xs font-medium text-muted-foreground">{t.results.notScored}</p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
