import type { Page, Route } from '@playwright/test'

export const CV = { cv_id: 'cv-1', language: 'en', extraction: 'text' }

export const ESTIMATE = {
  apify_usd: 0.04,
  llm_usd: 0.05,
  total_usd: 0.09,
  cap_usd: 1,
  within_cap: true,
  price_to_user_usd: 0.27,
}

/** Who is signed in. By default an owner account, which sees prices in dollars. */
export const OWNER = { user_id: 'user_owner', free_searches_left: 1, free_tailors_left: 1, unlimited: true, free_max_results: 10 }
export const FREE = { ...OWNER, user_id: 'user_free', unlimited: false }

type Handler = (route: Route) => unknown | Promise<unknown>
export type Handlers = Record<string, Handler>

export const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

/** Answers /api/* in the browser, so tests make no paid calls. Keys are "METHOD /path". */
export async function mockApi(page: Page, handlers: Handlers = {}) {
  const calls: { key: string; body: string | null }[] = []
  const defaults: Handlers = {
    'GET /me': (r) => json(r, OWNER),
    'POST /cv': (r) => json(r, CV, 201),
    'GET /cv/cv-1': (r) => json(r, CV),
    'DELETE /cv/cv-1': (r) => r.fulfill({ status: 204 }),
    'POST /estimate/search': (r) => json(r, ESTIMATE),
    'POST /estimate/tailor': (r) => json(r, ESTIMATE),
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace(/^\/api/, '')
    const key = `${request.method()} ${path}`
    calls.push({ key, body: request.postData() })
    const handler = handlers[key] ?? defaults[key]
    if (handler) return handler(route)
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"unmocked"}' })
  })
  return calls
}

export const pdfFile = (name = 'My CV.pdf', bytes = 2048) => ({
  name,
  mimeType: 'application/pdf',
  buffer: Buffer.alloc(bytes, 'a'),
})
