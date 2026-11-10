import { mkdirSync, writeFileSync } from 'node:fs'
import { clerk, clerkSetup } from '@clerk/testing/playwright'
import { expect, test as setup } from '@playwright/test'
import { AUTH_FILE, USER_ID_FILE } from './auth'

// Signs in once and saves the session; every other test starts from it.
// Source: https://clerk.com/docs/guides/development/testing/playwright/overview
//         https://clerk.com/docs/guides/development/testing/playwright/test-helpers
setup.describe.configure({ mode: 'serial' })

setup('get a Clerk testing token', async () => {
  await clerkSetup()
})

setup('sign in the test account', async ({ page }) => {
  // A test address you created on the sign-up page (see README). With the secret key, Clerk
  // signs it in without a password. Development keys only.
  const emailAddress = process.env.E2E_CLERK_USER_EMAIL ?? 'candor.demo+clerk_test@example.com'
  await page.goto('/')
  await clerk.signIn({ page, emailAddress })
  await page.goto('/account')
  await expect(page).toHaveURL(/\/account$/) // the server let the session in
  // Clerk loads in the page after the server has answered: wait for it to know the user
  const id = await (
    await page.waitForFunction(() => (window as unknown as { Clerk?: { user?: { id?: string } } }).Clerk?.user?.id)
  ).jsonValue()
  expect(id).toMatch(/^user_/)
  mkdirSync('e2e/.auth', { recursive: true })
  writeFileSync(USER_ID_FILE, id!)
  await page.context().storageState({ path: AUTH_FILE })
})
