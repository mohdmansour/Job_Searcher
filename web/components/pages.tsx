'use client'

import { useClerk, useUser } from '@clerk/nextjs'
import Link from 'next/link'
import { useState } from 'react'
import { Check, FileText, Trash2 } from 'lucide-react'
import { useApp } from '@/lib/app-state'
import { FileName } from '@/components/chrome'
import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function PricingView() {
  const { t } = useApp()
  const p = t.pricingPage
  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 md:py-16">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{p.title}</h1>
      <p className="mt-3 max-w-2xl text-muted-foreground">{p.body}</p>

      <ul className="mt-10 grid gap-4 md:grid-cols-2">
        <li className="flex flex-col rounded-xl border border-primary bg-card p-6 ring-1 ring-primary">
          <h2 className="text-xl font-semibold">{p.freeTitle}</h2>
          <ul className="mt-4 flex flex-col gap-3 text-sm">
            {p.freeItems.map((item) => (
              <li key={item} className="flex gap-2">
                <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
                {item}
              </li>
            ))}
          </ul>
          <Link href="/search" className={cn(buttonVariants({ size: 'lg' }), 'mt-6 h-11 self-start px-5')}>
            {p.freeCta}
          </Link>
        </li>
        <li className="flex flex-col rounded-xl border bg-card p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">{p.paidTitle}</h2>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{p.soon}</span>
          </div>
          <ul className="mt-4 flex flex-col gap-3 text-sm text-muted-foreground">
            {p.paidItems.map((item) => (
              <li key={item} className="flex gap-2">
                <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </li>
      </ul>
    </div>
  )
}

function AllowanceSection() {
  const { t, allowance } = useApp()
  const a = t.account
  return (
    <section aria-labelledby="allowance-h" className="rounded-xl border bg-card p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="allowance-h" className="text-sm font-medium text-muted-foreground">{t.allowance.label}</h2>
          {!allowance ? (
            <p className="mt-1 text-muted-foreground" aria-busy="true">…</p>
          ) : allowance.unlimited ? (
            <p className="mt-1 font-semibold">{a.unlimited}</p>
          ) : (
            <>
              <p className="mt-1 font-semibold" data-testid="account-allowance">
                {t.allowance.counts(allowance.free_searches_left, allowance.free_tailors_left)}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{a.allowanceNote}</p>
            </>
          )}
        </div>
        <Link href="/pricing" className={buttonVariants({ variant: 'outline', size: 'lg' })}>{a.plans}</Link>
      </div>
    </section>
  )
}

export function AccountView() {
  const { t, locale, setLocale, cv, deleteAllData } = useApp()
  const { user } = useUser()
  const { signOut } = useClerk()
  const [deleted, setDeleted] = useState(false)
  const [deleteFailed, setDeleteFailed] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const email = user?.primaryEmailAddress?.emailAddress

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 md:py-12">
      <h1 className="text-3xl font-semibold tracking-tight">{t.account.title}</h1>
      <div className="mt-8 flex flex-col gap-6">
        {/* Shown from Clerk in this browser only: the backend never stores a name or email. */}
        <section aria-labelledby="profile-h" className="flex flex-col gap-4 rounded-xl border bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 id="profile-h" className="text-sm font-medium text-muted-foreground">{t.account.profile}</h2>
            {user?.fullName && <p className="mt-1 font-semibold [overflow-wrap:anywhere]">{user.fullName}</p>}
            {email && <p className="text-sm text-muted-foreground [overflow-wrap:anywhere]" dir="ltr">{email}</p>}
          </div>
          <Button variant="outline" size="lg" onClick={() => signOut({ redirectUrl: '/' })}>{t.account.signOut}</Button>
        </section>

        <section aria-labelledby="cv-h" className="rounded-xl border bg-card p-5">
          <h2 id="cv-h" className="text-sm font-medium text-muted-foreground">{t.account.masterCv}</h2>
          {cv ? (
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <FileText aria-hidden="true" className="size-5 text-primary" />
                <div>
                  <p className="font-medium [overflow-wrap:anywhere]"><FileName name={cv.name} /></p>
                  <p className="text-sm text-muted-foreground">{t.search.detected(t.common.langNames[cv.language])}</p>
                </div>
              </div>
              <Link href="/search" className={buttonVariants({ variant: 'outline', size: 'lg' })}>{t.account.replace}</Link>
            </div>
          ) : (
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-muted-foreground">{deleted ? t.account.deleted : t.account.noCv}</p>
              <Link href="/search" className={buttonVariants({ size: 'lg' })}>{t.account.upload}</Link>
            </div>
          )}
        </section>

        <AllowanceSection />

        <section aria-labelledby="lang-h" className="rounded-xl border bg-card p-5">
          <h2 id="lang-h" className="font-semibold">{t.account.interface}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t.account.interfaceHint}</p>
          <div role="radiogroup" aria-labelledby="lang-h" className="mt-4 inline-flex rounded-lg border p-1">
            {(['en', 'ar'] as const).map((l) => (
              <button
                key={l}
                type="button"
                role="radio"
                aria-checked={locale === l}
                lang={l}
                onClick={() => setLocale(l)}
                className={cn('h-11 rounded-md px-4 text-sm font-medium', locale === l ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-muted')}
              >
                {l === 'en' ? 'English' : 'العربية'}
              </button>
            ))}
          </div>
        </section>

        <section aria-labelledby="data-h" className="rounded-xl border border-destructive/25 bg-card p-5">
          <h2 id="data-h" className="font-semibold">{t.account.data}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t.account.dataBody}</p>
          <Button
            variant="destructive"
            size="lg"
            className="mt-4 h-11 px-4"
            disabled={deleting}
            onClick={async () => {
              setDeleteFailed(false)
              setDeleting(true)
              try {
                await deleteAllData()
                setDeleted(true)
              } catch {
                setDeleteFailed(true)
              } finally {
                setDeleting(false)
              }
            }}
          >
            <Trash2 aria-hidden="true" />
            {t.account.delete}
          </Button>
          {deleted && <p role="status" className="mt-3 text-sm">{t.account.deleted}</p>}
          {deleteFailed && <p role="alert" className="mt-3 text-sm text-destructive">{t.errors.server}</p>}
        </section>
      </div>
    </div>
  )
}

export function LegalView({ kind }: { kind: 'privacy' | 'terms' }) {
  const { t } = useApp()
  const sections = kind === 'privacy' ? t.legal.privacy : t.legal.terms
  return (
    <article className="mx-auto max-w-2xl px-4 py-12 sm:px-6 md:py-16">
      <h1 className="text-3xl font-semibold tracking-tight">{kind === 'privacy' ? t.legal.privacyTitle : t.legal.termsTitle}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t.legal.updated}</p>
      <p className="mt-4 rounded-md bg-gap px-3 py-2 text-sm text-gap-foreground">{t.legal.demo}</p>
      <div className="mt-8 flex flex-col gap-6">
        {sections.map((s) => (
          <section key={s.h}>
            <h2 className="text-lg font-semibold">{s.h}</h2>
            <p className="mt-2 leading-relaxed text-foreground/85">{s.p}</p>
          </section>
        ))}
      </div>
    </article>
  )
}
