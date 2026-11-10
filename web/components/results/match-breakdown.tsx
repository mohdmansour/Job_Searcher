'use client'

import { CircleCheck, CircleDashed } from 'lucide-react'

export function ReasonList({ reasons }: { reasons: string[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {reasons.map((reason) => (
        <li key={reason} className="flex gap-3">
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-primary" />
          <p className="min-w-0 flex-1 [overflow-wrap:anywhere]" dir="auto">
            {reason}
          </p>
        </li>
      ))}
    </ul>
  )
}

export function SkillChips({ skills }: { skills: string[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {skills.map((skill) => (
        <li key={skill} className="max-w-full rounded-full bg-accent px-3 py-1 text-sm font-medium text-accent-foreground [overflow-wrap:anywhere]">
          <bdi>{skill}</bdi>
        </li>
      ))}
    </ul>
  )
}

export function GapList({ gaps }: { gaps: string[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {gaps.map((gap) => (
        <li key={gap} className="flex gap-3">
          <CircleDashed aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-gap-foreground" />
          <p className="min-w-0 flex-1 font-medium [overflow-wrap:anywhere]" dir="auto">
            {gap}
          </p>
        </li>
      ))}
    </ul>
  )
}
