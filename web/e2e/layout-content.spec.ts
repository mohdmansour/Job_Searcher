import { expect, test } from '@playwright/test'
import { owned } from './auth'
import { ESTIMATE, json, mockApi } from './mock-api'

// Deliberately awkward: very long unbroken words, mixed scripts, long lists.
const LONG = 'Supercalifragilisticexpialidocious'.repeat(4)
const now = new Date().toISOString()
const jobs = Array.from({ length: 12 }, (_, i) => ({
  job: {
    id: `linkedin:${i}`, source: 'linkedin', title: `Senior Quality Assurance Automation Engineer ${LONG}`,
    company: `${LONG} GmbH شركة الخليج للتجارة`, location: `${LONG}, عمّان، United Arab Emirates`, remote: i % 2 === 0,
    description: `See https://example.com/${LONG}/${LONG}\n\nنبحث عن محاسب ${LONG}`, url: 'https://www.linkedin.com/jobs/view/1',
    posted_at: now, fetched_at: now, language: 'en',
  },
  match: { score: 90 - i, reasons: [`Reason ${LONG}`, 'سبب باللغة العربية'], matched_skills: [LONG, 'SQL'], gaps: [`Gap ${LONG}`] },
  error: null,
}))
const handlers = {
  'GET /runs/run-1': (r: any) => json(r, { run_id: 'run-1', status: 'done', estimate: ESTIMATE, last_updated: now, from_cache: false, jobs, error: null }),
  'GET /tailor/t': (r: any) => json(r, {
    tailor_id: 't', status: 'running', estimate: ESTIMATE, error: null,
    results: [{
      job_id: 'linkedin:0', pdf_url: 'http://x/files/t/a.pdf', review_status: 'FAIL', attempts: 3, warning: true,
      remaining_violations: [{ adapted_text: LONG, problem: 'C', explanation: LONG, suggested_fix: LONG }],
      change_log: [{ original: LONG, adapted: LONG, why_faithful: LONG }],
    }],
  }),
}
const seed = JSON.stringify({
  cv: { id: 'cv-1', name: `${LONG}.pdf`, sizeKb: 186, language: 'en', extraction: 'ocr' },
  search: { title: LONG, country: 'United Arab Emirates', cities: Array.from({ length: 10 }, (_, i) => `${LONG}${i}`), remote: false, count: 25 },
  runId: 'run-1',
  selected: jobs.slice(0, 6).map((j) => j.job.id),
  batches: [{ id: 't', searchRunId: 'run-1', jobs: jobs.slice(0, 2).map((j) => ({ id: j.job.id, title: j.job.title, company: j.job.company })) }],
})

const noSideways = (page: import('@playwright/test').Page) =>
  expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth))
    .toBeLessThanOrEqual(0)

for (const locale of ['en', 'ar'] as const) {
  test.describe(locale, () => {
    test.beforeEach(async ({ page, context, baseURL }) => {
      await context.addCookies([{ name: 'locale', value: locale, url: baseURL! }])
      await mockApi(page, handlers)
      await page.addInitScript((v) => localStorage.setItem('nextrole.session.v1', v), owned(JSON.parse(seed)))
    })

    for (const path of ['/search', '/results', `/results?job=${encodeURIComponent('linkedin:0')}`, '/generate', '/account']) {
      test(`full content fits on ${path}`, async ({ page }) => {
        await page.goto(path)
        await page.waitForTimeout(800)
        await noSideways(page)
      })
    }

    test('the confirmation dialog fits and its buttons can be reached', async ({ page }) => {
      await page.goto('/results')
      await page.locator('div[role=region]').getByRole('button').last().click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      const box = (await dialog.boundingBox())!
      const view = page.viewportSize()!
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.y).toBeGreaterThanOrEqual(0)
      expect(box.x + box.width).toBeLessThanOrEqual(view.width)
      expect(box.y + box.height).toBeLessThanOrEqual(view.height)
      const button = (await dialog.getByRole('button').last().boundingBox())!
      expect(button.y + button.height).toBeLessThanOrEqual(view.height)
    })

    test('the bottom bar never hides the last job', async ({ page }) => {
      await page.goto('/results')
      const last = page.getByRole('listitem').last()
      await expect(last).toBeAttached()
      const bar = (await page.locator('div[role=region]').boundingBox())!
      // Very long pages take a moment to reach the end, so keep scrolling until they settle.
      await expect
        .poll(async () => {
          await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }))
          const job = (await last.boundingBox())!
          return job.y + job.height
        })
        .toBeLessThanOrEqual(bar.y)
    })
  })
}
