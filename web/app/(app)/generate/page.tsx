import type { Metadata } from 'next'
import { GenerateView } from '@/components/generate/generate-view'
import { requireAccount } from '@/lib/account-gate'

export const metadata: Metadata = { title: 'Tailored CVs — NextRole' }

export default async function GeneratePage() {
  await requireAccount('/generate')
  return <GenerateView />
}
