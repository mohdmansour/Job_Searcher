import type { Metadata } from 'next'
import { AccountView } from '@/components/pages'
import { requireAccount } from '@/lib/account-gate'

export const metadata: Metadata = { title: 'Account — NextRole' }

export default async function Page() {
  await requireAccount('/account')
  return <AccountView />
}
