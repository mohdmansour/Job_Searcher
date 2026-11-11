import { expect, test, type Page } from '@playwright/test'
import { owned, signedOut } from './auth'
import { ESTIMATE, FREE, json, mockApi, OWNER, pdfFile, type Handlers } from './mock-api'

// A9: the real free allowance replaces the demo credits. The backend enforces every limit;
// these tests check that the site shows it clearly and doesn't offer what will be refused.

const JOB = (id: string, title: string) => ({
  job: {
    id, source: 'linkedin', title, company: 'Acme', location: 'Berlin, Germany', remote: false, description: 'x',
    url: `https://www.linkedin.com/jobs/view/${id}`, posted_at: null, fetched_at: new Date().toISOString(), language: 'en',
  },
  match: { score: 70, reasons: ['r'], matched_skills: [], gaps: [] },
  error: null,
})
const doneRun = {
  run_id: 'run-1', status: 'done', estimate: ESTIMATE, last_updated: new Date().toISOString(), from_cache: false,
  jobs: [JOB('linkedin:1', 'Senior QA Engineer'), JOB('linkedin:2', 'Test Analyst')], error: null,
}

async function seed(page: Page, data: object) {
  await page.addInitScript((value) => {
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem('nextrole.session.v1', value)
      sessionStorage.setItem('seeded', '1')
    }
  }, owned(data))
}
const cv = { id: 'cv-1', name: 'My CV.pdf', sizeKb: 2, language: 'en', extraction: 'text' }
const searched = (selected: string[]) => ({
  cv, search: { title: 'QA', country: 'Germany', cities: [], remote: false, count: 10 }, runId: 'run-1', selected,
})
const asFree = (me: object = FREE, more: Handlers = {}): Handlers => ({ 'GET /me': (r) => json(r, me), ...more })

async function fillSearch(page: Page) {
  await page.locator('#job-title').fill('QA')
  await page.locator('#country').selectOption('Germany')
}

test.describe('a free account', () => {
  test('sees its allowance in the header, not demo credits', async ({ page }) => {
    await mockApi(page, asFree())
    await page.goto('/search')
    const pill = page.getByTestId('allowance')
    await expect(pill).toContainText('1 search · 1 CV')
    await expect(pill).not.toContainText(/credit|Demo/)
  })

  test('sees what the search uses instead of a price, and can only ask for 10 results', async ({ page }) => {
    const calls = await mockApi(page, asFree(FREE, {
      'POST /search': (r) => json(r, { run_id: 'run-1', status: 'queued', estimate: ESTIMATE }, 202),
      'GET /runs/run-1': (r) => json(r, doneRun),
    }))
    await seed(page, { cv })
    await page.goto('/search')
    await fillSearch(page)
    await expect(page.getByTestId('search-allowance')).toContainText('Free searches left: 1')
    await expect(page.getByTestId('search-price')).toHaveCount(0)
    await expect(page.getByRole('radio', { name: '25' })).toBeDisabled()
    await expect(page.getByRole('radio', { name: '50' })).toBeDisabled()
    await expect(page.getByRole('radio', { name: '10' })).toBeChecked()
    await expect(page.getByText('Free searches return up to 10 results. Paid plans with more results are coming soon.')).toBeVisible()
    await page.getByRole('button', { name: 'Start search' }).click()
    await expect(page).toHaveURL(/\/results/)
    expect(JSON.parse(calls.find((c) => c.key === 'POST /search')!.body!)).toMatchObject({ max_results: 10 })
  })

  test('with the free search used, explains it and offers no search', async ({ page }) => {
    await mockApi(page, asFree({ ...FREE, free_searches_left: 0 }))
    await seed(page, { cv })
    await page.goto('/search')
    await fillSearch(page)
    await expect(page.getByTestId('search-allowance')).toContainText('Paid plans are coming soon')
    await expect(page.getByRole('button', { name: 'Start search' })).toBeDisabled()
  })

  for (const [status, code, message] of [
    [403, 'allowance_used', /used your free allowance/],
    [429, 'rate_limited', /one search or tailoring at a time/],
    [429, 'daily_budget', /paused for the rest of today/],
  ] as const) {
    test(`a refused search (${code}) says why`, async ({ page }) => {
      await mockApi(page, asFree(FREE, { 'POST /search': (r) => json(r, { detail: { code } }, status) }))
      await seed(page, { cv })
      await page.goto('/search')
      await fillSearch(page)
      await page.getByRole('button', { name: 'Start search' }).click()
      await expect(page.getByRole('alert').getByText(message)).toBeVisible()
    })
  }

  test('a fourth upload in a day says why', async ({ page }) => {
    await mockApi(page, asFree(FREE, { 'POST /cv': (r) => json(r, { detail: { code: 'rate_limited' } }, 429) }))
    await page.goto('/search')
    await page.locator('input[type=file]').setInputFiles(pdfFile())
    await expect(page.getByRole('alert').getByText(/up to 3 CVs a day/)).toBeVisible()
  })

  test('can’t confirm more CVs than it has left', async ({ page }) => {
    await mockApi(page, asFree(FREE, { 'GET /runs/run-1': (r) => json(r, doneRun) }))
    await seed(page, searched(['linkedin:1', 'linkedin:2']))
    await page.goto('/results')
    await page.getByRole('button', { name: 'Review & generate' }).click()
    await expect(page.getByTestId('tailor-allowance')).toContainText('Select no more than 1')
    await expect(page.getByTestId('tailor-price')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Confirm and generate' })).toBeDisabled()
    await page.getByRole('button', { name: /Remove Test Analyst/ }).click()
    await expect(page.getByTestId('tailor-allowance')).toContainText('This uses 1 free CV')
    await expect(page.getByRole('button', { name: 'Confirm and generate' })).toBeEnabled()
  })

  test('the allowance is shown again after a run finishes', async ({ page }) => {
    let me = FREE
    await mockApi(page, {
      'GET /me': (r) => json(r, me),
      'POST /search': (r) => {
        me = { ...FREE, free_searches_left: 0 }
        return json(r, { run_id: 'run-1', status: 'queued', estimate: ESTIMATE }, 202)
      },
      'GET /runs/run-1': (r) => json(r, doneRun),
    })
    await seed(page, { cv })
    await page.goto('/search')
    await fillSearch(page)
    await page.getByRole('button', { name: 'Start search' }).click()
    await expect(page.getByTestId('allowance')).toContainText('0 searches · 1 CV')
  })

  test('sees it all in Arabic', async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: 'locale', value: 'ar', url: baseURL! }])
    await mockApi(page, asFree({ ...FREE, free_searches_left: 0 }))
    await seed(page, { cv })
    await page.goto('/search')
    await expect(page.getByTestId('allowance')).toContainText('سيرة: 1')
    await page.locator('#job-title').fill('QA')
    await page.locator('#country').selectOption('Germany')
    await expect(page.getByTestId('search-allowance')).toContainText('الخطط المدفوعة قادمة قريبًا')
  })
})

test.describe('an owner account', () => {
  test('has no limits and still sees prices in dollars', async ({ page }) => {
    await mockApi(page, asFree(OWNER))
    await seed(page, { cv })
    await page.goto('/search')
    await expect(page.getByTestId('allowance')).toContainText('No limits')
    await fillSearch(page)
    await expect(page.getByTestId('search-price')).toHaveText('$0.27')
    await expect(page.getByRole('radio', { name: '50' })).toBeEnabled()
  })
})

test.describe('signed out', () => {
  test.use(signedOut)
  test('on a public page, nothing is asked and no allowance is shown', async ({ page }) => {
  const calls = await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('banner')).toBeVisible()
  await expect(page.getByTestId('allowance')).toHaveCount(0)
  expect(calls.filter((c) => c.key === 'GET /me')).toEqual([])
  })
})
