import { ClerkProvider } from '@clerk/nextjs'
import { enUS } from '@clerk/localizations'
import { clerkArabic } from '@/lib/clerk-arabic'
import type { Metadata, Viewport } from 'next'
import { IBM_Plex_Sans, IBM_Plex_Sans_Arabic } from 'next/font/google'
import { cookies } from 'next/headers'
import { AppStateProvider } from '@/lib/app-state'
import { clerkAppearance } from '@/lib/clerk-appearance'
import type { Locale } from '@/lib/i18n'
import './globals.css'

const plex = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-plex',
})

const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ['arabic'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-plex-arabic',
})

export const metadata: Metadata = {
  title: 'Candor — Tailor your CV. Keep it honest.',
  description:
    'Upload your master CV, find matching LinkedIn jobs, see your strengths and gaps, and download an honest tailored PDF for each role.',
  icons: {
    icon: [
      { url: '/icon-light-32x32.png', media: '(prefers-color-scheme: light)' },
      { url: '/icon-dark-32x32.png', media: '(prefers-color-scheme: dark)' },
      { url: '/icon.svg', type: 'image/svg+xml' },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  viewportFit: 'cover', // lets the bottom bar respect the phone's safe area
  colorScheme: 'light',
  themeColor: '#fbf9f5',
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies()
  const locale: Locale = cookieStore.get('locale')?.value === 'ar' ? 'ar' : 'en'

  return (
    <html lang={locale} dir={locale === 'ar' ? 'rtl' : 'ltr'} className={`${plex.variable} ${plexArabic.variable}`}>
      <body className="min-h-dvh antialiased">
        <ClerkProvider appearance={clerkAppearance} localization={locale === 'ar' ? clerkArabic : enUS /* named, not undefined: Clerk keeps the last language otherwise */}>
          <AppStateProvider initialLocale={locale}>{children}</AppStateProvider>
        </ClerkProvider>
      </body>
    </html>
  )
}
