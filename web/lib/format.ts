import type { Locale } from './i18n'

/** Always "$0.27": the Arabic currency format renders as a garbled "US$" inside right-to-left text. */
export function formatUsd(amount: number): string {
  const format = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return amount > 0 && amount < 0.01 ? `< ${format.format(0.01)}` : format.format(amount)
}

export function formatDateTime(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-AE' : 'en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(iso))
}

export function daysAgo(iso: string, now = Date.now()): number {
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / 86_400_000))
}
