import type { Metadata } from 'next'
import { LegalView } from '@/components/pages'

export const metadata: Metadata = { title: 'Privacy — NextRole' }

export default function Page() {
  return <LegalView kind="privacy" />
}
