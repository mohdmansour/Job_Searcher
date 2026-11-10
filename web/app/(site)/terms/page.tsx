import type { Metadata } from 'next'
import { LegalView } from '@/components/pages'

export const metadata: Metadata = { title: 'Terms — Candor' }

export default function Page() {
  return <LegalView kind="terms" />
}
