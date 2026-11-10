import { expect, test, type Page } from '@playwright/test'
import { owned, signedOut } from './auth'
import { FREE, json, mockApi } from './mock-api'

// A10 + A11: real accounts replace the demo sign-in and credits.

const CV = { id: 'cv-1', name: 'My CV.pdf', sizeKb: 2, language: 'ar', extraction: 'text' }

async function seed(page: Page, value: string) {
  await page.addInitScript((value) => {
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem('candor.session.v1', value)
      sessionStorage.setItem('seeded', '1')
    }
  }, value)
}
const stored = (page: Page) => page.evaluate(() => localStorage.getItem('candor.session.v1') ?? '')

test.describe('signed out', () => {
  test.use(signedOut)

  test('upload & search sends a new visitor to sign-up, and back afterwards', async ({ page }) => {
    await page.goto('/search')
    await expect(page).toHaveURL(/\/sign-up\?redirect_url=.*%2Fsearch/)
    await expect(page.locator('.cl-signUp-root')).toBeVisible()
  })

  for (const path of ['/results', '/generate', '/account']) {
    test(`${path} asks for sign-in`, async ({ page }) => {
      await page.goto(path)
      await expect(page).toHaveURL(new RegExp(`/sign-in\\?redirect_url=.*${encodeURIComponent(path)}`))
    })
  }

  test('the public pages stay open', async ({ page }) => {
    for (const path of ['/', '/pricing', '/privacy', '/terms']) {
      await page.goto(path)
      await expect(page).toHaveURL(new RegExp(`${path}$`))
    }
  })

  test('Clerk’s screens follow the site language, there and back', async ({ page }) => {
    await page.goto('/sign-up')
    await expect(page.locator('.cl-headerTitle')).toHaveText('Create your account')
    await page.getByRole('banner').getByRole('button', { name: 'Switch interface to Arabic' }).click()
    await expect(page.locator('.cl-headerTitle')).toHaveText('أنشاء حساب جديد')
    await page.getByRole('banner').getByRole('button', { name: 'تغيير لغة الواجهة إلى الإنجليزية' }).click()
    await expect(page.locator('.cl-headerTitle')).toHaveText('Create your account') // Clerk once stayed in Arabic here
  })

  test('the header offers sign-in', async ({ page }) => {
    await page.goto('/')
    const menu = page.getByRole('button', { name: 'Open menu' })
    if (await menu.isVisible()) await menu.click() // phones keep it in the menu
    await expect(page.getByRole('banner').getByRole('link', { name: 'Sign in' }).first()).toBeAttached()
  })
})

test('the pricing page sells nothing yet and moves no money', async ({ page }) => {
  const calls = await mockApi(page)
  await page.goto('/pricing')
  await expect(page.getByRole('heading', { name: 'Free' })).toBeVisible()
  await expect(page.getByText('Coming soon', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Add to balance|Buy/ })).toHaveCount(0)
  expect(calls.filter((c) => c.key !== 'GET /me')).toEqual([])
})

test('the account page shows the real account and allowance, with no demo parts', async ({ page }) => {
  await mockApi(page, { 'GET /me': (r) => json(r, FREE) })
  await page.goto('/account')
  await expect(page.getByText(/\+clerk_test@/)).toBeVisible() // the signed-in test address, from Clerk
  await expect(page.getByTestId('account-allowance')).toHaveText('1 search · 1 CV')
  await expect(page.getByText(/Demo|credits?/)).toHaveCount(0) // case-sensitive: the test email contains "demo"
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
})

test('delete my data clears the server from any device, then this browser', async ({ page }) => {
  const calls = await mockApi(page, { 'DELETE /me/data': (r) => r.fulfill({ status: 204 }) })
  await seed(page, owned({ cv: CV, search: { title: 'SECRET-TITLE', country: 'Germany', cities: [], remote: false, count: 10 } }))
  await page.goto('/account')
  await expect(page.getByText('My CV.pdf')).toBeVisible()
  await expect(page.getByText('Detected CV language: Arabic')).toBeVisible()
  await page.getByRole('button', { name: 'Delete my data' }).click()
  await expect(page.getByText('Your CV, searches and tailored files have been deleted.').first()).toBeVisible()
  expect(calls.map((c) => c.key)).toContain('DELETE /me/data')
  await expect.poll(() => stored(page)).not.toContain('My CV.pdf')
  expect(await stored(page)).not.toContain('SECRET-TITLE')
})

test('delete my data works with nothing stored in this browser (another device)', async ({ page }) => {
  const calls = await mockApi(page, { 'DELETE /me/data': (r) => r.fulfill({ status: 204 }) })
  await page.goto('/account')
  await page.getByRole('button', { name: 'Delete my data' }).click()
  await expect(page.getByRole('status')).toHaveText('Your CV, searches and tailored files have been deleted.')
  expect(calls.map((c) => c.key)).toContain('DELETE /me/data')
})

test('if deletion fails, it says so and keeps the CV listed', async ({ page }) => {
  await mockApi(page, { 'DELETE /me/data': (r) => r.fulfill({ status: 500 }) })
  await seed(page, owned({ cv: CV }))
  await page.goto('/account')
  await expect(page.getByText('My CV.pdf')).toBeVisible()
  await page.getByRole('button', { name: 'Delete my data' }).click()
  await expect(page.getByText(/Something went wrong/)).toBeVisible()
  await expect(page.getByText('My CV.pdf')).toBeVisible()
})

test('data another account left in this browser is removed, not shown', async ({ page }) => {
  const calls = await mockApi(page)
  await seed(page, JSON.stringify({ owner: 'user_someone_else', cv: { ...CV, name: 'THEIR-CV.pdf' }, search: { title: 'THEIR-SEARCH', country: 'Germany', cities: [], remote: false, count: 10 } }))
  await page.goto('/search')
  await expect(page.getByRole('button', { name: 'Choose a file' })).toBeVisible()
  await expect(page.getByText('THEIR-CV.pdf')).toHaveCount(0)
  await expect(page.locator('#job-title')).toHaveValue('')
  await expect.poll(() => stored(page)).not.toContain('THEIR-')
  expect(calls.map((c) => c.key)).not.toContain('GET /cv/cv-1') // their id is never even used
})

test('the site makes no third-party requests', async ({ page }) => {
  const outside: string[] = []
  page.on('request', (r) => {
    const url = new URL(r.url())
    // Clerk is the one outside service the site is allowed to use, for sign-in.
    const clerk = /\.clerk\.accounts\.dev$|^img\.clerk\.com$|\.protect\.clerk\.com$|^challenges\.cloudflare\.com$/.test(url.hostname)
    if (url.protocol.startsWith('http') && url.hostname !== 'localhost' && !clerk) outside.push(r.url())
  })
  await mockApi(page)
  for (const path of ['/', '/search', '/account']) await page.goto(path)
  expect(outside).toEqual([])
})
