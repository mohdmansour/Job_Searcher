import { expect, test, type Download, type Page } from '@playwright/test'
import { owned } from './auth'
import { ESTIMATE, json, mockApi, type Handlers } from './mock-api'

const JOBS = [
  {
    job: {
      id: 'linkedin:1', source: 'linkedin', title: 'Senior QA Engineer', company: 'Acme', location: 'Berlin, Germany',
      remote: false, description: 'Line one of the posting.\nLine two.', url: 'https://www.linkedin.com/jobs/view/1',
      posted_at: new Date(Date.now() - 3 * 86_400_000).toISOString(), fetched_at: new Date().toISOString(), language: 'en',
    },
    match: { score: 72, reasons: ['Strong API testing background'], matched_skills: ['Postman', 'SQL'], gaps: ['Selenium'] },
    error: null,
  },
  {
    job: {
      id: 'linkedin:2', source: 'linkedin', title: 'Test Analyst', company: 'Globex', location: 'Germany',
      remote: true, description: 'Second posting.', url: 'javascript:alert(1)',
      posted_at: null, fetched_at: new Date().toISOString(), language: 'en',
    },
    match: null,
    error: 'TimeoutError',
  },
]

const doneRun = {
  run_id: 'run-1', status: 'done', estimate: ESTIMATE, last_updated: new Date().toISOString(),
  from_cache: false, jobs: JOBS, error: null,
}

const session = (extra: object = {}) => ({
  cv: { id: 'cv-1', name: 'My CV.pdf', sizeKb: 2, language: 'en', extraction: 'text' },
  search: { title: 'QA', country: 'Germany', cities: [], remote: false, count: 10 },
  runId: 'run-1',
  ...extra,
})

async function seed(page: Page, data: object) {
  await page.addInitScript((value) => {
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem('nextrole.session.v1', value)
      sessionStorage.setItem('seeded', '1')
    }
  }, owned(data))
}

const run = (handlers: Handlers = {}): Handlers => ({ 'GET /runs/run-1': (r) => json(r, doneRun), ...handlers })

// Phones show the list and the job separately; desktop shows both.
async function openFirstJob(page: Page) {
  if ((page.viewportSize()?.width ?? 0) < 1024) await page.getByRole('link', { name: 'Senior QA Engineer' }).click()
}

// ---------------- W6: search form ----------------
test.describe('search form', () => {
  test('lists all 27 countries and sends the exact form values', async ({ page }) => {
    const calls = await mockApi(page, {
      'POST /search': (r) => json(r, { run_id: 'run-1', status: 'queued', estimate: ESTIMATE }, 202),
      'GET /runs/run-1': (r) => json(r, doneRun),
    })
    await seed(page, { cv: session().cv })
    await page.goto('/search')
    await expect(page.locator('#country option')).toHaveCount(28) // 27 and the placeholder

    await page.locator('#job-title').fill('QA Engineer')
    await page.locator('#country').selectOption('United Arab Emirates')
    await page.getByRole('button', { name: 'Dubai' }).click()
    await page.getByPlaceholder('Type a city and press Enter').fill('Al Ain')
    await page.getByPlaceholder('Type a city and press Enter').press('Enter')
    await page.getByText('Remote jobs only').click()
    await page.locator('label', { hasText: /^50$/ }).click()
    await page.getByRole('button', { name: 'Start search' }).click()

    await expect(page.getByRole('heading', { name: 'Ranked matches' })).toBeVisible()
    const sent = JSON.parse(calls.find((c) => c.key === 'POST /search')!.body!)
    expect(sent).toMatchObject({
      cv_id: 'cv-1', title: 'QA Engineer', country: 'United Arab Emirates',
      cities: ['Dubai', 'Al Ain'], remote: true, max_results: 50, force_refresh: false,
    })
  })

  test('a city can be removed and duplicates are ignored', async ({ page }) => {
    await mockApi(page)
    await page.goto('/search')
    const box = page.getByPlaceholder('Type a city and press Enter')
    for (const city of ['Berlin', 'berlin']) {
      await box.fill(city)
      await box.press('Enter')
    }
    await expect(page.getByRole('button', { name: 'Remove Berlin' })).toHaveCount(1)
    await page.getByRole('button', { name: 'Remove Berlin' }).click()
    await expect(page.getByRole('button', { name: 'Remove Berlin' })).toHaveCount(0)
  })

  test('extra job titles are sent, limited to 2, and shown in the results summary', async ({ page }) => {
    const calls = await mockApi(page, {
      'POST /search': (r) => json(r, { run_id: 'run-1', status: 'queued', estimate: ESTIMATE }, 202),
      'GET /runs/run-1': (r) => json(r, doneRun),
    })
    await seed(page, { cv: session().cv })
    await page.goto('/search')
    await page.locator('#job-title').fill('QA Engineer')
    await page.locator('#country').selectOption('Jordan')
    const box = page.getByPlaceholder('Type a title and press Enter')
    for (const title of ['Software Tester', 'software tester', 'QC Engineer']) {
      await box.fill(title)
      await box.press('Enter')
    }
    await expect(page.getByText('You can add up to 2 more titles.')).toBeVisible()
    await expect(box).toBeDisabled()
    await page.getByRole('button', { name: 'Start search' }).click()
    await expect(page.getByText(/QA Engineer \/ Software Tester \/ QC Engineer/)).toBeVisible()
    expect(JSON.parse(calls.find((c) => c.key === 'POST /search')!.body!)).toMatchObject({
      title: 'QA Engineer', more_titles: ['Software Tester', 'QC Engineer'],
    })
  })

  test('stops at 10 cities', async ({ page }) => {
    await mockApi(page)
    await page.goto('/search')
    const box = page.getByPlaceholder('Type a city and press Enter')
    for (let i = 1; i <= 10; i++) {
      await box.fill(`City ${i}`)
      await box.press('Enter')
    }
    await expect(page.getByText('You can add up to 10 cities.')).toBeVisible()
    await expect(box).toBeDisabled()
  })

  test('requires a CV, title and country', async ({ page }) => {
    const calls = await mockApi(page)
    await page.goto('/search')
    await page.getByRole('button', { name: 'Start search' }).click()
    await expect(page.getByText('Upload a CV before starting a search.')).toBeVisible()
    await expect(page.getByText('Enter a job title.')).toBeVisible()
    await expect(page.getByText('Choose a country to search in.')).toBeVisible()
    expect(calls.filter((c) => c.key === 'POST /search')).toHaveLength(0)
  })

  test('Arabic names are shown while the English value is sent', async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: 'locale', value: 'ar', url: baseURL! }])
    await mockApi(page)
    await page.goto('/search')
    await expect(page.locator('#country option', { hasText: 'ألمانيا' })).toHaveAttribute('value', 'Germany')
  })
})

// ---------------- W7: running a search ----------------
test.describe('running a search', () => {
  test('shows the real price before anything starts', async ({ page }) => {
    const calls = await mockApi(page)
    await seed(page, { cv: session().cv })
    await page.goto('/search')
    await page.locator('#country').selectOption('Germany')
    await expect(page.getByTestId('search-price')).toHaveText('$0.27')
    expect(calls.map((c) => c.key)).not.toContain('POST /search')
  })

  test('search stays locked until the price is shown', async ({ page }) => {
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    await mockApi(page, {
      'POST /estimate/search': async (r) => {
        await held
        await json(r, ESTIMATE)
      },
    })
    await seed(page, { cv: session().cv })
    await page.goto('/search')
    await page.locator('#job-title').fill('QA')
    await page.locator('#country').selectOption('Germany')
    await expect(page.getByRole('button', { name: 'Start search' })).toBeDisabled()
    release()
    await expect(page.getByTestId('search-price')).toHaveText('$0.27')
    await expect(page.getByRole('button', { name: 'Start search' })).toBeEnabled()
  })

  test('over the cap: explains and refuses to start', async ({ page }) => {
    await mockApi(page, { 'POST /estimate/search': (r) => json(r, { ...ESTIMATE, within_cap: false }) })
    await seed(page, { cv: session().cv })
    await page.goto('/search')
    await page.locator('#country').selectOption('Germany')
    await expect(page.getByText(/over the cost limit/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start search' })).toBeDisabled()
  })

  test('zero demo credits never block a real search', async ({ page }) => {
    await mockApi(page)
    await seed(page, { cv: session().cv, demo: { credits: 0, history: [], charged: [] } })
    await page.goto('/search')
    await page.locator('#job-title').fill('QA')
    await page.locator('#country').selectOption('Germany')
    await expect(page.getByTestId('search-price')).toHaveText('$0.27')
    await expect(page.getByRole('button', { name: 'Start search' })).toBeEnabled()
  })

  test('waits, survives a reload, then shows results', async ({ page }) => {
    let finished = false
    await mockApi(page, {
      'GET /runs/run-1': (r) => json(r, finished ? doneRun : { ...doneRun, status: 'running', jobs: [], last_updated: null }),
    })
    await seed(page, session())
    await page.goto('/results')
    await expect(page.getByText('Searching LinkedIn postings…')).toBeVisible()
    await page.reload()
    await expect(page.getByText('Searching LinkedIn postings…')).toBeVisible()
    finished = true
    await expect(page.getByRole('heading', { name: 'Ranked matches' })).toBeVisible({ timeout: 10_000 })
  })

  for (const [name, body, message] of [
    ['failed', { ...doneRun, status: 'failed', jobs: [] }, 'The search didn’t finish. Please try again.'],
    ['over the cap', { ...doneRun, status: 'stopped_cost_cap', jobs: [] }, /reached the cost limit/],
    ['no results', { ...doneRun, jobs: [] }, 'No matching postings found'],
  ] as const) {
    test(`end state: ${name}`, async ({ page }) => {
      await mockApi(page, { 'GET /runs/run-1': (r) => json(r, body) })
      await seed(page, session())
      await page.goto('/results')
      await expect(page.getByText(message)).toBeVisible()
      await expect(page.getByRole('link', { name: 'Edit search' })).toBeVisible()
    })
  }

  test('an expired run explains itself', async ({ page }) => {
    await mockApi(page, { 'GET /runs/run-1': (r) => r.fulfill({ status: 404 }) })
    await seed(page, session())
    await page.goto('/results')
    await expect(page.getByText(/deleted automatically after 24 hours/)).toBeVisible()
  })

  test('with no search yet, points back to the form', async ({ page }) => {
    await mockApi(page)
    await page.goto('/results')
    await expect(page.getByText('No search yet')).toBeVisible()
    await expect(page.getByText('Load demo results')).toHaveCount(0)
  })
})

// ---------------- W8: results ----------------
test.describe('results', () => {
  test('shows the backend’s real match details', async ({ page }) => {
    await mockApi(page, run())
    await seed(page, session())
    await page.goto('/results')
    await openFirstJob(page)
    await expect(page.getByText('Strong API testing background')).toBeVisible()
    await expect(page.getByText('Postman', { exact: true })).toBeVisible()
    await expect(page.getByText('Selenium', { exact: true })).toBeVisible()
    await expect(page.getByText('Posted 3 days ago')).toBeVisible()
    await expect(page.getByRole('link', { name: 'View on LinkedIn' })).toHaveAttribute('href', 'https://www.linkedin.com/jobs/view/1')
    await expect(page.getByText(/Line one of the posting/)).toBeVisible()
  })

  test('a job that couldn’t be scored explains itself, with no date or unsafe link', async ({ page }) => {
    await mockApi(page, run())
    await seed(page, session())
    await page.goto(`/results?job=${encodeURIComponent('linkedin:2')}`)
    await expect(page.getByText(/couldn’t score this job/)).toBeVisible()
    await expect(page.getByText(/^Posted/)).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'View on LinkedIn' })).toHaveCount(0)
  })

  test('on phones, list and job are separate views', async ({ page }) => {
    test.skip((page.viewportSize()?.width ?? 0) >= 1024, 'phone only')
    await mockApi(page, run())
    await seed(page, session())
    await page.goto('/results')
    await expect(page.getByRole('heading', { name: 'Full job description' })).toBeHidden()
    await page.getByRole('link', { name: 'Senior QA Engineer' }).click()
    await expect(page.getByRole('heading', { name: 'Full job description' })).toBeVisible()
    await page.getByRole('link', { name: 'Back to results' }).click()
    await expect(page.getByRole('heading', { name: 'Ranked matches' })).toBeVisible()
  })
})

// ---------------- W9: refresh and selection ----------------
test.describe('refresh and selection', () => {
  test('refresh asks first, shows the price, then forces new data', async ({ page }) => {
    let n = 0
    const calls = await mockApi(page, run({
      'POST /search': (r) => {
        n++
        return json(r, { run_id: 'run-1', status: 'queued', estimate: ESTIMATE }, 202)
      },
    }))
    await seed(page, session())
    await page.goto('/results')
    await page.getByRole('button', { name: 'Refresh jobs' }).click()
    await expect(page.getByRole('dialog').getByText('$0.27')).toBeVisible()
    expect(n).toBe(0)
    await page.getByRole('button', { name: 'Refresh now' }).click()
    await expect.poll(() => n).toBe(1)
    expect(JSON.parse(calls.find((c) => c.key === 'POST /search')!.body!).force_refresh).toBe(true)
  })

  test('confirming sends the jobs and extra information, and doesn’t store it', async ({ page }) => {
    const calls = await mockApi(page, run({
      'POST /tailor': (r) => json(r, { run_id: 'tailor-1', status: 'queued', estimate: ESTIMATE }, 202),
      'GET /tailor/tailor-1': (r) => json(r, { tailor_id: 'tailor-1', status: 'running', estimate: ESTIMATE, results: [], error: null }),
    }))
    await seed(page, session({ selected: ['linkedin:1'] }))
    await page.goto('/results')
    await page.getByRole('button', { name: 'Review & generate' }).click()
    await expect(page.getByTestId('tailor-price')).toHaveText('$0.27')
    await page.locator('#extra-info').fill('SECRET-EXTRA-DETAIL')
    await page.getByRole('button', { name: 'Confirm and generate' }).click()
    await expect(page.getByRole('heading', { name: 'Tailored CVs' })).toBeVisible()
    expect(JSON.parse(calls.find((c) => c.key === 'POST /tailor')!.body!)).toEqual({
      run_id: 'run-1', job_ids: ['linkedin:1'], user_extra_info: 'SECRET-EXTRA-DETAIL', confirmed: [],
    })
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('SECRET-EXTRA-DETAIL')
  })

  test('tailoring stays locked until the price is shown', async ({ page }) => {
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    await mockApi(page, run({
      'POST /estimate/tailor': async (r) => {
        await held
        await json(r, ESTIMATE)
      },
    }))
    await seed(page, session({ selected: ['linkedin:1'] }))
    await page.goto('/results')
    await page.getByRole('button', { name: 'Review & generate' }).click()
    await expect(page.getByRole('button', { name: 'Confirm and generate' })).toBeDisabled()
    release()
    await expect(page.getByRole('button', { name: 'Confirm and generate' })).toBeEnabled()
  })

  test('over the cap: asks for fewer jobs', async ({ page }) => {
    await mockApi(page, run({ 'POST /estimate/tailor': (r) => json(r, { ...ESTIMATE, within_cap: false }) }))
    await seed(page, session({ selected: ['linkedin:1', 'linkedin:2'] }))
    await page.goto('/results')
    await page.getByRole('button', { name: 'Review & generate' }).click()
    await expect(page.getByText(/too many jobs for one run/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Confirm and generate' })).toBeDisabled()
  })
})

// ---------------- missing skills ticked before tailoring ----------------
test.describe('missing skills in the review box', () => {
  const withMissing = {
    ...doneRun,
    jobs: [
      { ...JOBS[0], match: { ...JOBS[0].match!, missing_skills: ['Python', 'VLANs'] } },
      { ...JOBS[1], match: { score: 40, reasons: ['r'], matched_skills: [], gaps: ['g'], missing_skills: ['python', 'Jira'] } },
    ],
  }
  const openReview = async (page: Page, selected: string[], runBody: object = withMissing, more: Handlers = {}, review = 'Review & generate') => {
    const calls = await mockApi(page, { 'GET /runs/run-1': (r) => json(r, runBody), ...more })
    await seed(page, session({ selected }))
    await page.goto('/results')
    await page.getByRole('button', { name: review }).click()
    return calls
  }

  test('lists each missing skill once, and sends the ticked ones with their details', async ({ page }) => {
    const calls = await openReview(page, ['linkedin:1', 'linkedin:2'], withMissing, {
      'POST /tailor': (r) => json(r, { run_id: 'tailor-1', status: 'queued', estimate: ESTIMATE }, 202),
      'GET /tailor/tailor-1': (r) => json(r, { tailor_id: 'tailor-1', status: 'running', estimate: ESTIMATE, results: [], error: null }),
    })
    const box = page.getByTestId('missing-skills')
    await expect(box.getByRole('checkbox')).toHaveCount(3) // Python, VLANs, Jira: "python" is the same skill
    await box.getByRole('checkbox', { name: 'Python' }).click()
    await box.getByLabel('Details for Python (optional)').fill('SECRET-SKILL-DETAIL 2 years')
    await box.getByRole('checkbox', { name: 'Jira' }).click()
    await expect(box.getByText(/Only tick what’s true/)).toBeVisible()
    await page.getByRole('button', { name: 'Confirm and generate' }).click()
    await expect(page.getByRole('heading', { name: 'Tailored CVs' })).toBeVisible()
    expect(JSON.parse(calls.find((c) => c.key === 'POST /tailor')!.body!)).toMatchObject({
      confirmed: [{ label: 'Python', details: 'SECRET-SKILL-DETAIL 2 years' }, { label: 'Jira', details: '' }],
    })
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('SECRET-SKILL-DETAIL')
  })

  test('jobs scored before this feature show no list', async ({ page }) => {
    await openReview(page, ['linkedin:1'], doneRun)
    await expect(page.getByTestId('missing-skills')).toHaveCount(0)
  })

  test('works in Arabic', async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: 'locale', value: 'ar', url: baseURL! }])
    await openReview(page, ['linkedin:1'], withMissing, {}, 'المراجعة والإنشاء')
    await expect(page.getByTestId('missing-skills')).toContainText('مهارات تطلبها هذه الوظائف ولا تظهر في سيرتك')
  })
})

// ---------------- W10 and W11: tailoring ----------------
const PASSED = {
  job_id: 'linkedin:1', pdf_url: 'http://127.0.0.1:8000/files/tailor-1/CV-QA.pdf', review_status: 'PASS', attempts: 1, warning: false,
  remaining_violations: [],
  change_log: [{ original: 'Taught math', adapted: 'Delivered math lessons', why_faithful: 'Same activity' }],
}
const batch = { id: 'tailor-1', searchRunId: 'run-1', jobs: [{ id: 'linkedin:1', title: 'Senior QA Engineer', company: 'Acme' }, { id: 'linkedin:2', title: 'Test Analyst', company: 'Globex' }] }
const tailorRun = (status: string, results: object[]) => ({ tailor_id: 'tailor-1', status, estimate: ESTIMATE, results, error: null })

test.describe('tailoring', () => {
  const card = (page: Page, title: string) => page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: title }) })

  test('progress arrives job by job, and no score is shown after tailoring', async ({ page }) => {
    let results: object[] = []
    let status = 'running'
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun(status, results)) }))
    await seed(page, session({ batches: [batch] }))
    await page.goto('/generate')
    await expect(page.getByText('0 of 2 ready')).toBeVisible()
    results = [PASSED]
    await expect(page.getByText('1 of 2 ready')).toBeVisible({ timeout: 10_000 })
    await expect(card(page, 'Senior QA Engineer').getByRole('link', { name: 'Download PDF' })).toBeVisible()
    await expect(card(page, 'Test Analyst').locator('[aria-current=step]')).toHaveText('Tailoring and checking')
    results = [PASSED, { ...PASSED, job_id: 'linkedin:2', pdf_url: 'http://127.0.0.1:8000/files/tailor-1/CV-2.pdf' }]
    status = 'done'
    await expect(page.getByText('2 of 2 ready')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('72%')).toHaveCount(0)
  })

  test('downloads through the website, not the backend address', async ({ page }) => {
    await mockApi(page, run({
      'GET /tailor/tailor-1': (r) => json(r, tailorRun('done', [PASSED])),
    }))
    // The link opens a new tab as a phone fallback, so the file is answered for the whole browser context.
    await page.context().route('**/api/files/tailor-1/CV-QA.pdf', (r) =>
      r.fulfill({ status: 200, contentType: 'application/pdf', headers: { 'content-disposition': 'attachment; filename="CV-QA.pdf"' }, body: '%PDF-1.4 test' }),
    )
    await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
    await page.goto('/generate')
    const link = page.getByRole('link', { name: 'Download PDF' })
    await expect(link).toHaveAttribute('href', '/api/files/tailor-1/CV-QA.pdf')
    const downloaded = new Promise<Download>((resolve) => {
      page.on('download', resolve)
      page.context().on('page', (tab) => tab.on('download', resolve))
    })
    await link.click()
    expect((await downloaded).suggestedFilename()).toBe('CV-QA.pdf')
  })

  test('shows the real change log', async ({ page }) => {
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun('done', [PASSED])) }))
    await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
    await page.goto('/generate')
    for (const text of ['Taught math', 'Delivered math lessons', 'Same activity']) await expect(page.getByText(text)).toBeVisible()
  })

  test('fixes and rewordings show before and after; moved lines and suggestions are listed', async ({ page }) => {
    const result = {
      ...PASSED,
      change_log: [
        { original: 'Colaborated with third-party', adapted: 'Collaborated with third parties', why_faithful: 'Spelling and grammar only', kind: 'fixed' },
        { original: 'Conducted manual testing', adapted: 'Performed manual functional testing', why_faithful: 'Same activity', kind: 'reworded' },
        { original: 'MOVED-LINE stays as written', adapted: 'MOVED-LINE stays as written', why_faithful: 'Moved up', kind: 'moved' },
      ],
      suggestions: [{ label: 'Results in numbers', text: 'If you have a result in numbers, add it.', kind: 'add' }],
    }
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun('done', [result])) }))
    await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
    await page.goto('/generate')
    const changes = page.getByTestId('changes')
    await expect(changes.getByText('Fixed', { exact: true })).toBeVisible()
    await expect(changes.getByText('Reworded for this job')).toBeVisible()
    await expect(changes.getByText('Collaborated with third parties')).toBeVisible()
    await expect(changes.getByText('MOVED-LINE')).toHaveCount(0) // no fake before-and-after
    await expect(page.getByTestId('moved')).toContainText('Moved higher for this job')
    await expect(page.getByTestId('moved')).toContainText('MOVED-LINE stays as written')
    await expect(page.getByTestId('suggestions')).toContainText('If you have a result in numbers, add it.')
  })

  test('results made before these labels existed still show', async ({ page }) => {
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun('done', [PASSED])) }))
    await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
    await page.goto('/generate')
    await expect(page.getByTestId('changes')).toContainText('Delivered math lessons')
    await expect(page.getByTestId('suggestions')).toHaveCount(0)
  })

  test.describe('regenerating with suggestions', () => {
    const SUGGESTED = {
      ...PASSED,
      redo_available: true,
      suggestions: [
        { label: 'Python', text: 'If you use Python, add it with examples.', kind: 'add' },
        { label: 'VLANs', text: 'If you have set up VLANs, add it.', kind: 'add' },
        { label: 'Skill spelling', text: 'If "and communications" is a typo, fix it in your CV.', kind: 'tip' },
      ],
    }
    const open = async (page: Page, result: object, more: Handlers = {}) => {
      const calls = await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun('done', [result])), ...more }))
      await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
      await page.goto('/generate')
      return calls
    }

    test('tick suggestions, add details, and regenerate that CV', async ({ page }) => {
      const calls = await open(page, SUGGESTED, {
        'POST /tailor/tailor-1/redo': (r) => json(r, { run_id: 'tailor-2', status: 'queued', estimate: ESTIMATE }, 202),
        'GET /tailor/tailor-2': (r) => json(r, tailorRun('running', [])),
      })
      const panel = page.getByTestId('suggestions')
      await expect(panel.getByRole('button', { name: /Regenerate/ })).toHaveCount(0) // nothing ticked yet
      await panel.getByRole('checkbox', { name: /Python/ }).click()
      await panel.getByLabel('Details for Python (optional)').fill('SECRET-DETAIL 2 years at Acme')
      await panel.getByRole('checkbox', { name: /VLANs/ }).click()
      await expect(panel.getByText('Only tick what’s true: it will appear on your CV.')).toBeVisible()
      await panel.getByRole('button', { name: 'Regenerate with 2 selected' }).click()
      await expect(panel.getByRole('status')).toHaveText(/Regenerating/)
      await expect(page.getByText('New version', { exact: true })).toBeVisible() // listed next to the earlier one,
      await expect(page.getByRole('link', { name: 'Download PDF' })).toHaveCount(1) // which keeps its PDF
      expect(JSON.parse(calls.find((c) => c.key === 'POST /tailor/tailor-1/redo')!.body!)).toEqual({
        job_id: 'linkedin:1',
        confirmed: [{ label: 'Python', details: 'SECRET-DETAIL 2 years at Acme' }, { label: 'VLANs', details: '' }],
      })
      expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('SECRET-DETAIL')
    })

    test('a tip has no tick box', async ({ page }) => {
      await open(page, SUGGESTED)
      const panel = page.getByTestId('suggestions')
      await expect(panel.getByText(/and communications/)).toBeVisible()
      await expect(panel.getByRole('checkbox')).toHaveCount(2)
    })

    test('with the free regeneration used, suggestions are listed without tick boxes', async ({ page }) => {
      await open(page, { ...SUGGESTED, redo_available: false })
      const panel = page.getByTestId('suggestions')
      await expect(panel.getByText('If you use Python, add it with examples.')).toBeVisible()
      await expect(panel.getByRole('checkbox')).toHaveCount(0)
    })

    test('a refused regeneration says why', async ({ page }) => {
      await open(page, SUGGESTED, {
        'POST /tailor/tailor-1/redo': (r) => json(r, { detail: { code: 'redo_used' } }, 403),
      })
      const panel = page.getByTestId('suggestions')
      await panel.getByRole('checkbox', { name: /Python/ }).click()
      await panel.getByRole('button', { name: 'Regenerate with 1 selected' }).click()
      await expect(panel.getByRole('alert')).toHaveText('This CV has already been regenerated once for free.')
    })

    test('works in Arabic', async ({ page, context, baseURL }) => {
      await context.addCookies([{ name: 'locale', value: 'ar', url: baseURL! }])
      await open(page, SUGGESTED)
      const panel = page.getByTestId('suggestions')
      await panel.getByRole('checkbox', { name: /Python/ }).click()
      await expect(panel.getByRole('button', { name: 'أعد الإنشاء بما حدّدته (1)' })).toBeVisible()
    })
  })

  test('warning: lists remaining problems and still offers the PDF', async ({ page }) => {
    const warned = {
      ...PASSED, review_status: 'FAIL', attempts: 3, warning: true,
      remaining_violations: [{ adapted_text: 'Led a team of ten', problem: 'C', explanation: 'The original has no team size', suggested_fix: 'Remove the number' }],
    }
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun('done', [warned])) }))
    await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
    await page.goto('/generate')
    await expect(page.getByText('Check before you send this')).toBeVisible()
    for (const text of ['Led a team of ten', 'The original has no team size', /Remove the number/]) await expect(page.getByText(text)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Download PDF' })).toBeVisible()
  })

  test('failed run: keeps finished PDFs and retry starts a new run for that job only', async ({ page }) => {
    const calls = await mockApi(page, run({
      'GET /tailor/tailor-1': (r) => json(r, tailorRun('failed', [PASSED])),
      'POST /tailor': (r) => json(r, { run_id: 'tailor-2', status: 'queued', estimate: ESTIMATE }, 202),
      'GET /tailor/tailor-2': (r) => json(r, { ...tailorRun('running', []), tailor_id: 'tailor-2' }),
    }))
    await seed(page, session({ batches: [batch] }))
    await page.goto('/generate')
    await expect(page.getByText('This job wasn’t finished')).toBeVisible()
    await expect(card(page, 'Senior QA Engineer').getByRole('link', { name: 'Download PDF' })).toBeVisible()
    await card(page, 'Test Analyst').getByRole('button', { name: 'Retry this job' }).click()
    await expect(page.getByText('This job wasn’t finished')).toHaveCount(0)
    await expect(card(page, 'Senior QA Engineer').getByRole('link', { name: 'Download PDF' })).toBeVisible()
    expect(JSON.parse(calls.find((c) => c.key === 'POST /tailor')!.body!)).toMatchObject({ run_id: 'run-1', job_ids: ['linkedin:2'] })
  })

  test('cost cap: says so and keeps finished PDFs', async ({ page }) => {
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => json(r, tailorRun('stopped_cost_cap', [PASSED])) }))
    await seed(page, session({ batches: [batch] }))
    await page.goto('/generate')
    await expect(page.getByText(/reached the cost limit/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Download PDF' })).toBeVisible()
  })

  test('expired files: explains, with no retry', async ({ page }) => {
    await mockApi(page, run({ 'GET /tailor/tailor-1': (r) => r.fulfill({ status: 404 }) }))
    await seed(page, session({ batches: [{ ...batch, jobs: [batch.jobs[0]] }] }))
    await page.goto('/generate')
    await expect(page.getByText('These files are no longer available')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry this job' })).toHaveCount(0)
  })

  test('with nothing tailored, points back to results', async ({ page }) => {
    await mockApi(page)
    await page.goto('/generate')
    await expect(page.getByText('Nothing generating')).toBeVisible()
  })
})
