import { expect, test } from '@playwright/test'
import { FREE, json, mockApi } from './mock-api'

const PAGES = ['/', '/search', '/results', '/generate', '/account', '/pricing', '/privacy', '/terms']
const SIGN_IN_PAGES = ['/sign-in', '/sign-up']

for (const locale of ['en', 'ar'] as const) {
  for (const path of [...PAGES, ...SIGN_IN_PAGES]) {
    test(`${path} has no sideways scroll (${locale})`, async ({ page, context, baseURL }) => {
      // sign-in and sign-up are seen by signed-out visitors
      if (SIGN_IN_PAGES.includes(path)) await context.clearCookies()
      await context.addCookies([{ name: 'locale', value: locale, url: baseURL! }])
      await page.goto(path)
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr')
      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))
      expect(scrollWidth, `page is ${scrollWidth}px wide on a ${clientWidth}px screen`).toBeLessThanOrEqual(clientWidth)
    })
  }
}

// The header carries the free allowance once it is known: the longest form must still fit.
for (const locale of ['en', 'ar'] as const) {
  test(`the header with the free allowance fits (${locale})`, async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: 'locale', value: locale, url: baseURL! }])
    await mockApi(page, { 'GET /me': (r) => json(r, { ...FREE, free_searches_left: 10, free_tailors_left: 10 }) })
    await page.goto('/search')
    await expect(page.getByTestId('allowance')).toBeVisible()
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(scrollWidth, `page is ${scrollWidth}px wide on a ${clientWidth}px screen`).toBeLessThanOrEqual(clientWidth)
  })
}
