import { expect, test } from '@playwright/test'
import { owned } from './auth'
import { CV, json, mockApi, pdfFile } from './mock-api'

const fileInput = 'input[type=file]'

test('uploads a CV, showing progress', async ({ page }) => {
  let release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  const calls = await mockApi(page, {
    'POST /cv': async (r) => {
      await held
      await json(r, { ...CV, language: 'ar', extraction: 'ocr' }, 201)
    },
  })
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles(pdfFile())
  // Interception can hide upload-progress events, so either phase may show here.
  await expect(page.getByText(/Uploading…|Reading your CV…/)).toBeVisible()
  release()
  await expect(page.getByText('My CV.pdf')).toBeVisible()
  await expect(page.getByText('Detected CV language: Arabic')).toBeVisible()
  await expect(page.getByText(/scanned or unusual PDF/)).toBeVisible()
  expect(calls.filter((c) => c.key === 'POST /cv')).toHaveLength(1)
})

test('an Arabic file name keeps its extension at the end', async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: 'locale', value: 'ar', url: baseURL! }])
  await mockApi(page)
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles(pdfFile('سيرتي 2026.pdf'))
  const name = page.getByTestId('file-name')
  await expect(name).toHaveAttribute('dir', 'rtl')
  await expect(name.locator('bdi').last()).toHaveText('.pdf')
  await expect(name.locator('bdi').last()).toHaveAttribute('dir', 'ltr')
})

test('only one upload runs at a time, and search waits for it', async ({ page }) => {
  let release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  const calls = await mockApi(page, {
    'POST /cv': async (r) => {
      await held
      await json(r, CV, 201)
    },
  })
  await page.goto('/search')
  await page.locator('#job-title').fill('QA')
  await page.locator('#country').selectOption('Germany')
  await page.locator(fileInput).setInputFiles(pdfFile('One.pdf'))
  await expect(page.getByText(/Uploading…|Reading your CV…/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start search' })).toBeDisabled()
  await page.locator(fileInput).setInputFiles(pdfFile('Two.pdf'))
  release()
  await expect(page.getByText('One.pdf')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start search' })).toBeEnabled()
  expect(calls.filter((c) => c.key === 'POST /cv')).toHaveLength(1)
})

test('the sample CV option is gone', async ({ page }) => {
  await mockApi(page)
  await page.goto('/search')
  await expect(page.getByRole('button', { name: 'Choose a file' })).toBeVisible()
  await expect(page.getByText('Use the sample CV')).toHaveCount(0)
})

test('a reload keeps the CV', async ({ page }) => {
  await mockApi(page)
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles(pdfFile())
  await expect(page.getByRole('button', { name: 'Replace' })).toBeVisible({ timeout: 20_000 }) // upload finished
  await expect.poll(() => page.evaluate(() => localStorage.getItem('nextrole.session.v1'))).toContain('My CV.pdf')
  await page.reload()
  await expect(page.getByText('My CV.pdf')).toBeVisible()
})

test('an expired CV is cleared with an explanation', async ({ page }) => {
  await mockApi(page, { 'GET /cv/cv-1': (r) => r.fulfill({ status: 404 }) })
  await page.addInitScript(
    (v) => localStorage.setItem('nextrole.session.v1', v),
    owned({ cv: { id: 'cv-1', name: 'Old.pdf', sizeKb: 2, language: 'en', extraction: 'text' } }),
  )
  await page.goto('/search')
  await expect(page.getByText(/deleted automatically/)).toBeVisible()
  await expect(page.getByText('Old.pdf')).toHaveCount(0)
})

test('removing deletes the CV on the backend', async ({ page }) => {
  const calls = await mockApi(page)
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles(pdfFile())
  await page.getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByRole('button', { name: 'Choose a file' })).toBeVisible()
  expect(calls.map((c) => c.key)).toContain('DELETE /cv/cv-1')
})

test('replacing uploads the new CV, then deletes the old one', async ({ page }) => {
  let n = 0
  const calls = await mockApi(page, {
    'POST /cv': (r) => json(r, { ...CV, cv_id: `cv-${++n}` }, 201),
    'DELETE /cv/cv-1': (r) => r.fulfill({ status: 204 }),
  })
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles(pdfFile('First.pdf'))
  await expect(page.getByRole('button', { name: 'Replace' })).toBeVisible({ timeout: 20_000 }) // upload finished
  await page.locator(fileInput).setInputFiles(pdfFile('Second.pdf'))
  await expect(page.getByText('Second.pdf')).toBeVisible()
  await expect(page.getByText('First.pdf')).toHaveCount(0)
  await expect.poll(() => calls.map((c) => c.key)).toContain('DELETE /cv/cv-1')
})

test('refuses non-PDFs and oversized files before sending', async ({ page }) => {
  const calls = await mockApi(page)
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles({ name: 'cv.docx', mimeType: 'application/msword', buffer: Buffer.from('x') })
  await expect(page.getByText(/isn’t a PDF/)).toBeVisible()
  await page.locator(fileInput).setInputFiles(pdfFile('Big.pdf', 10 * 1024 * 1024 + 1))
  await expect(page.getByText(/too large/)).toBeVisible()
  expect(calls.filter((c) => c.key === 'POST /cv')).toHaveLength(0)
})

for (const [status, message] of [
  [400, /couldn’t read this file/],
  [413, /too large/],
  [503, /can’t read scanned/],
  [500, /Something went wrong/],
] as const) {
  test(`shows a clear message for a ${status}`, async ({ page }) => {
    await mockApi(page, { 'POST /cv': (r) => r.fulfill({ status }) })
    await page.goto('/search')
    await page.locator(fileInput).setInputFiles(pdfFile())
    await expect(page.getByRole('alert').getByText(message)).toBeVisible()
  })
}

test('shows Arabic messages in the Arabic interface', async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: 'locale', value: 'ar', url: baseURL! }])
  await mockApi(page, { 'POST /cv': (r) => r.fulfill({ status: 500 }) })
  await page.goto('/search')
  await page.locator(fileInput).setInputFiles(pdfFile())
  await expect(page.getByRole('alert').getByText(/حدث خطأ/)).toBeVisible()
})
