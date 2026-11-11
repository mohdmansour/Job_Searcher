import type { Metadata } from 'next'
import { PricingView } from '@/components/pages'

export const metadata: Metadata = { title: 'Pricing — NextRole' }

export default function Page() {
  return <PricingView />
}
