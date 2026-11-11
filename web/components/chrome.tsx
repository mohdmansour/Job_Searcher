'use client'

import { useAuth, UserButton } from '@clerk/nextjs'
import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { Coins, Languages, Menu, X } from 'lucide-react'
import { useApp } from '@/lib/app-state'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn('flex items-center gap-2 font-semibold tracking-tight text-foreground', className)}>
      <Image src="/logo-mark.png" alt="" width={32} height={32} priority className="size-8" />
      <span dir="ltr" className="text-lg max-[359px]:sr-only">
        Next<span className="text-primary">Role</span>
      </span>
    </Link>
  )
}

export function LanguageToggle({ className }: { className?: string }) {
  const { locale, setLocale, t } = useApp()
  const next = locale === 'en' ? 'ar' : 'en'
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      aria-label={t.common.switchToLabel}
      className={cn(buttonVariants({ variant: 'ghost', size: 'lg' }), 'gap-2 px-3', className)}
    >
      <Languages aria-hidden="true" />
      <span lang={next}>{t.common.switchTo}</span>
    </button>
  )
}

/** The real free allowance from the backend. Hidden until it is known (e.g. signed out). */
export function AllowancePill() {
  const { allowance, t } = useApp()
  if (!allowance) return null
  return (
    <Link
      href="/pricing"
      data-testid="allowance"
      className="inline-flex h-11 items-center gap-1.5 rounded-full border bg-card px-2.5 text-sm font-medium whitespace-nowrap hover:bg-muted sm:h-9 sm:px-3"
    >
      <Coins aria-hidden="true" className="hidden size-4 text-primary min-[400px]:block" />
      <span className="sr-only">{t.allowance.label}: </span>
      {allowance.unlimited ? (
        t.allowance.unlimited
      ) : (
        <>
          <span className="hidden min-[400px]:inline">{t.allowance.freePrefix}</span>
          {t.allowance.counts(allowance.free_searches_left, allowance.free_tailors_left)}
        </>
      )}
    </Link>
  )
}

export function SiteHeader() {
  const { t } = useApp()
  const { isSignedIn } = useAuth()
  const [open, setOpen] = useState(false)
  const links = [
    { href: '/#how', label: t.nav.how },
    { href: '/pricing', label: t.nav.pricing },
    { href: '/#faq', label: t.nav.faq },
  ]
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <Logo />
        <nav aria-label={t.nav.mainLabel} className="hidden md:block">
          <ul className="flex items-center gap-1">
            {links.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className={cn(buttonVariants({ variant: 'ghost', size: 'lg' }), 'px-3 text-muted-foreground')}>
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ms-auto hidden items-center gap-2 md:flex">
          <LanguageToggle />
          {!isSignedIn && (
            <Link href="/sign-in" className={cn(buttonVariants({ variant: 'ghost', size: 'lg' }), 'px-3')}>
              {t.common.signIn}
            </Link>
          )}
          <Link href="/search" className={cn(buttonVariants({ size: 'lg' }), 'px-4')}>
            {isSignedIn ? t.common.openApp : t.common.getStarted}
          </Link>
        </div>
        <div className="ms-auto flex items-center gap-1 md:hidden">
          <LanguageToggle className="px-2" />
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? t.common.closeMenu : t.common.openMenu}
            className={buttonVariants({ variant: 'ghost', size: 'icon-lg' })}
          >
            {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label={t.nav.mainLabel} className="border-t px-4 py-3 md:hidden">
          <ul className="flex flex-col gap-1">
            {[...links, ...(isSignedIn ? [] : [{ href: '/sign-in', label: t.common.signIn }])].map((l) => (
              <li key={l.href}>
                <Link href={l.href} onClick={() => setOpen(false)} className="block rounded-md px-3 py-2.5 hover:bg-muted">
                  {l.label}
                </Link>
              </li>
            ))}
            <li className="pt-2">
              <Link href="/search" onClick={() => setOpen(false)} className={cn(buttonVariants({ size: 'lg' }), 'h-11 w-full')}>
                {isSignedIn ? t.common.openApp : t.common.getStarted}
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  )
}

export function AppHeader() {
  const { t } = useApp()
  const pathname = usePathname()
  const steps = [
    { href: '/search', label: t.nav.search },
    { href: '/results', label: t.nav.results },
    { href: '/generate', label: t.nav.downloads },
  ]
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:px-6">
        <Logo />
        <nav aria-label={t.nav.appSteps} className="ms-4 hidden lg:block">
          <ol className="flex items-center gap-1">
            {steps.map((s, i) => {
              const current = pathname.startsWith(s.href)
              return (
                <li key={s.href}>
                  <Link
                    href={s.href}
                    aria-current={current ? 'page' : undefined}
                    className={cn(
                      'flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground',
                      current && 'bg-accent text-accent-foreground hover:bg-accent',
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        'grid size-5 place-items-center rounded-full border text-[11px]',
                        current && 'border-primary bg-primary text-primary-foreground',
                      )}
                    >
                      {i + 1}
                    </span>
                    {s.label}
                  </Link>
                </li>
              )
            })}
          </ol>
        </nav>
        <div className="ms-auto flex items-center gap-1 sm:gap-2">
          <AllowancePill />
          <LanguageToggle className="hidden px-2 sm:inline-flex" />
          <Link
            href="/account"
            aria-current={pathname === '/account' ? 'page' : undefined}
            className={cn(buttonVariants({ variant: 'ghost', size: 'lg' }), 'hidden px-3 sm:inline-flex')}
          >
            {t.nav.account}
          </Link>
          <LanguageToggle className="px-2 sm:hidden" />
          {/* phones reach the account, and Sign out, through the Account tab below */}
          <span className="hidden size-11 place-items-center sm:grid">
            <UserButton />
          </span>
        </div>
      </div>
      <nav aria-label={t.nav.appSteps} className="border-t lg:hidden">
        <ol className="mx-auto grid max-w-7xl grid-cols-4 text-center text-xs font-medium">
          {[...steps, { href: '/account', label: t.nav.account }].map((s) => {
            const current = pathname.startsWith(s.href)
            return (
              <li key={s.href}>
                <Link
                  href={s.href}
                  aria-current={current ? 'page' : undefined}
                  className={cn(
                    'flex min-h-11 items-center justify-center border-b-2 border-transparent px-1 py-2 text-muted-foreground',
                    current && 'border-primary text-foreground',
                  )}
                >
                  {s.label}
                </Link>
              </li>
            )
          })}
        </ol>
      </nav>
    </header>
  )
}

export function SiteFooter() {
  const { t } = useApp()
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div className="max-w-sm space-y-3">
          <Logo />
          <p className="text-sm leading-relaxed text-muted-foreground">{t.footer.line}</p>
          <p className="text-xs text-muted-foreground">{t.footer.rights}</p>
        </div>
        <nav aria-label={t.nav.footerLabel}>
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <li><Link className="hover:underline" href="/pricing">{t.nav.pricing}</Link></li>
            <li><Link className="hover:underline" href="/account">{t.nav.account}</Link></li>
            <li><Link className="hover:underline" href="/privacy">{t.nav.privacy}</Link></li>
            <li><Link className="hover:underline" href="/terms">{t.nav.terms}</Link></li>
          </ul>
        </nav>
      </div>
    </footer>
  )
}

/** Keeps ".pdf" at the end of the name: otherwise "CV 2026.pdf" in Arabic renders as "CV pdf.2026". */
export function FileName({ name }: { name: string }) {
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  const extension = dot > 0 ? name.slice(dot) : ''
  return (
    <span dir={/[\u0600-\u06FF]/.test(stem) ? 'rtl' : 'ltr'} data-testid="file-name">
      <bdi>{stem}</bdi>
      <bdi dir="ltr">{extension}</bdi>
    </span>
  )
}

export function ScoreBadge({ score, size = 'md' }: { score: number; size?: 'md' | 'lg' }) {
  const tone = score >= 75 ? 'text-primary' : score >= 60 ? 'text-foreground' : 'text-muted-foreground'
  return (
    <div className={cn('flex flex-col items-end gap-1', size === 'lg' && 'items-stretch')}>
      <span className={cn('font-semibold tabular-nums', tone, size === 'lg' ? 'text-3xl' : 'text-lg leading-none')}>
        {score}%
      </span>
      <span aria-hidden="true" className={cn('h-1.5 overflow-hidden rounded-full bg-muted', size === 'lg' ? 'w-full' : 'w-12')}>
        <span className="block h-full rounded-full bg-primary" style={{ width: `${score}%` }} />
      </span>
    </div>
  )
}
