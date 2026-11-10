import type { Metadata } from 'next'
import { Suspense } from 'react'
import { ResultsView } from '@/components/results/results-view'
import { requireAccount } from '@/lib/account-gate'

export const metadata: Metadata = { title: 'Ranked matches — Candor' }

export default async function ResultsPage() {
  await requireAccount('/results')
  return (
    <Suspense>
      <ResultsView />
    </Suspense>
  )
}
