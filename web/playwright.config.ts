import { defineConfig, devices } from '@playwright/test'
import { AUTH_FILE } from './e2e/auth'

// The test sign-in needs the Clerk keys the site uses (development keys only). They stay in
// .env.local and are never printed.
try {
  process.loadEnvFile('.env.local')
} catch {
  // no file: Clerk's setup step reports the missing keys
}
process.env.CLERK_PUBLISHABLE_KEY ??= process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

// Layout runs at every size; flow tests run at one phone and one desktop size.
const LAYOUT_ONLY = 'layout*.spec.ts'

const phone = (width: number, height: number) => ({
  ...devices['Pixel 7'],
  viewport: { width, height },
})

const signedIn = { dependencies: ['setup'] }

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  workers: 4,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:3000' },
  projects: [
    { name: 'setup', testMatch: /global\.setup\.ts/, use: { storageState: undefined } },
    { name: 'phone-320', testMatch: LAYOUT_ONLY, use: { ...phone(320, 640), storageState: AUTH_FILE }, ...signedIn },
    { name: 'phone-360', testMatch: LAYOUT_ONLY, use: { ...phone(360, 740), storageState: AUTH_FILE }, ...signedIn },
    { name: 'phone-390', use: { ...phone(390, 844), storageState: AUTH_FILE }, ...signedIn },
    { name: 'tablet-768', testMatch: LAYOUT_ONLY, use: { viewport: { width: 768, height: 1024 }, storageState: AUTH_FILE }, ...signedIn },
    { name: 'desktop-1280', use: { viewport: { width: 1280, height: 800 }, storageState: AUTH_FILE }, ...signedIn },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
