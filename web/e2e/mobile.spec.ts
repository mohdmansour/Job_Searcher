import { expect, test } from '@playwright/test'
import { owned } from './auth'
import { ESTIMATE, json, mockApi } from './mock-api'

test.beforeEach(({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 1024, 'touch screens only')
})

const job = {
  job: { id: 'linkedin:1', source: 'linkedin', title: 'QA', company: 'Acme', location: 'Dubai', remote: false, description: 'x', url: 'https://www.linkedin.com/jobs/view/1', posted_at: null, fetched_at: new Date().toISOString(), language: 'en' },
  match: { score: 70, reasons: ['r'], matched_skills: ['s'], gaps: ['g'] },
  error: null,
}
const handlers = {
  'GET /runs/run-1': (r: any) => json(r, { run_id: 'run-1', status: 'done', estimate: ESTIMATE, last_updated: new Date().toISOString(), from_cache: false, jobs: [job], error: null }),
  'GET /tailor/t': (r: any) => json(r, { tailor_id: 't', status: 'failed', estimate: ESTIMATE, results: [], error: 'x' }),
}
const session = {
  cv: { id: 'cv-1', name: 'My CV.pdf', sizeKb: 2, language: 'en', extraction: 'text' },
  search: { title: 'QA', country: 'United Arab Emirates', cities: ['Dubai'], remote: false, count: 25 },
  runId: 'run-1',
  selected: ['linkedin:1'],
  batches: [{ id: 't', searchRunId: 'run-1', jobs: [{ id: 'linkedin:1', title: 'QA', company: 'Acme' }] }],
}

for (const path of ['/search', '/results', '/generate', '/account', '/pricing', '/sign-in', '/']) {
  test(`controls are finger-sized on ${path}`, async ({ page }) => {
    await mockApi(page, handlers)
    await page.addInitScript((v) => localStorage.setItem('nextrole.session.v1', v), owned(session))
    await page.goto(path)
    await page.waitForTimeout(800)
    const small = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>("[class*='group/button'], select, [data-slot='input'], header nav a, header a[href='/pricing']")]
        .filter((el) => el.offsetParent !== null)
        .map((el) => ({ text: (el.textContent || el.tagName).trim().slice(0, 30), h: el.getBoundingClientRect().height }))
        .filter((el) => el.h < 43.5),
    )
    expect(small).toEqual([])
  })
}

test('the job checkbox can be tapped just outside its small box', async ({ page }) => {
  await mockApi(page, handlers)
  await page.addInitScript((v) => localStorage.setItem('nextrole.session.v1', v), owned({ ...session, selected: [] }))
  await page.goto('/results')
  const box = page.getByRole('checkbox')
  await expect(box).not.toBeChecked()
  const b = (await box.boundingBox())!
  await page.touchscreen.tap(b.x + b.width + 8, b.y + b.height / 2)
  await expect(box).toBeChecked()
})

test('the CV picker accepts PDFs and opens from the button', async ({ page }) => {
  await mockApi(page)
  await page.goto('/search')
  await expect(page.locator('input[type=file]')).toHaveAttribute('accept', /application\/pdf/)
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.getByRole('button', { name: 'Choose a file' }).click()])
  expect(chooser.isMultiple()).toBe(false)
})
