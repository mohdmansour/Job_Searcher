import type { Metadata } from 'next'
import { SearchForm, SearchPageHeader } from '@/components/search/search-form'
import { requireAccount } from '@/lib/account-gate'

export const metadata: Metadata = { title: 'Upload & search — NextRole' }

export default async function SearchPage() {
  await requireAccount('/search', 'sign-up')
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 md:py-12">
      <SearchPageHeader />
      <SearchForm />
    </div>
  )
}
