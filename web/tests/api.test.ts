import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, connectAuth, isFinished, pdfHref, poll } from '@/lib/api'

function respondWith(status: number, body?: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  connectAuth(async () => null, () => {})
})

describe('requests', () => {
  it('goes through the website proxy and sends JSON', async () => {
    const fetchMock = respondWith(202, { run_id: 'r1', status: 'queued', estimate: {} })
    await api.startSearch({ cv_id: 'c', title: 'QA', country: 'Germany', cities: [], remote: false, max_results: 10 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/search')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({ title: 'QA', max_results: 10 })
  })

  it('encodes ids placed in the path', async () => {
    const fetchMock = respondWith(200, { cv_id: 'a/b', language: 'en', extraction: 'text' })
    await api.getCv('a/b')
    expect(fetchMock.mock.calls[0][0 as never]).toBe('/api/cv/a%2Fb')
  })

  it('deleting returns nothing on 204', async () => {
    respondWith(204)
    await expect(api.deleteCv('c')).resolves.toBeUndefined()
  })
})

describe('signing in', () => {
  it('sends the session token on every request', async () => {
    const fetchMock = respondWith(200, { run_id: 'r' })
    connectAuth(async () => 'token-1', () => {})
    await api.getRun('r')
    const init = fetchMock.mock.calls[0][1 as never] as RequestInit
    expect(init.headers).toMatchObject({ Authorization: 'Bearer token-1' })
  })

  it('sends no header when signed out', async () => {
    const fetchMock = respondWith(200, { run_id: 'r' })
    await api.getRun('r')
    expect((fetchMock.mock.calls[0][1 as never] as RequestInit).headers).toEqual({})
  })

  it('keeps JSON headers next to the token', async () => {
    const fetchMock = respondWith(200, { ok: true })
    connectAuth(async () => 't', () => {})
    await api.estimateTailor(1)
    expect((fetchMock.mock.calls[0][1 as never] as RequestInit).headers).toEqual({ 'Content-Type': 'application/json', Authorization: 'Bearer t' })
  })

  it('a 401 reports that the session ended', async () => {
    respondWith(401, { detail: 'x' })
    const signedOut = vi.fn()
    connectAuth(async () => 't', signedOut)
    await expect(api.getRun('r')).rejects.toMatchObject({ code: 'unauthorized' })
    expect(signedOut).toHaveBeenCalledOnce()
  })

  it('failing to get a token is a connection problem, not a signed-out user', async () => {
    connectAuth(async () => { throw new Error('clerk failed') }, () => {})
    await expect(api.getRun('r')).rejects.toMatchObject({ code: 'network' })
  })
})

describe('errors', () => {
  it.each([
    [400, 'rejected'],
    [402, 'cost_cap'],
    [404, 'expired'],
    [413, 'too_large'],
    [422, 'rejected'],
    [500, 'server'],
    [503, 'unavailable'],
  ])('status %i becomes %s', async (status, code) => {
    respondWith(status, { detail: 'x' })
    await expect(api.getRun('r')).rejects.toMatchObject({ name: 'ApiError', code })
  })

  it('a failed connection is a network error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    await expect(api.getRun('r')).rejects.toMatchObject({ code: 'network' })
  })
})

describe('pdfHref', () => {
  it('turns the backend address into a website path', () => {
    expect(pdfHref('http://127.0.0.1:8000/files/t1/CV%20QA.pdf')).toBe('/api/files/t1/CV%20QA.pdf')
  })
})

describe('isFinished', () => {
  it.each([
    ['queued', false],
    ['running', false],
    ['done', true],
    ['failed', true],
    ['stopped_cost_cap', true],
  ])('%s -> %s', (status, expected) => {
    expect(isFinished(status)).toBe(expected)
  })
})

describe('poll', () => {
  const quick = { intervalMs: 1 }

  it('waits while the page is hidden, then resumes', async () => {
    let wake = () => {}
    const page = {
      hidden: true,
      addEventListener: (_: string, fn: () => void) => { wake = fn },
      removeEventListener: () => {},
    }
    vi.stubGlobal('document', page)
    const fetcher = vi.fn(async () => ({ status: 'done' }))
    const running = poll(fetcher, (v) => isFinished(v.status), () => {}, quick)
    await new Promise((r) => setTimeout(r, 20))
    expect(fetcher).not.toHaveBeenCalled()
    page.hidden = false
    wake()
    await running
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('reports each update and stops at an end state', async () => {
    const seen: string[] = []
    const fetcher = vi.fn<() => Promise<{ status: string }>>()
      .mockResolvedValueOnce({ status: 'queued' })
      .mockResolvedValueOnce({ status: 'running' })
      .mockResolvedValueOnce({ status: 'done' })
    const last = await poll(fetcher, (v) => isFinished(v.status), (v) => seen.push(v.status), quick)
    expect(seen).toEqual(['queued', 'running', 'done'])
    expect(last).toEqual({ status: 'done' })
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('stops when aborted', async () => {
    const controller = new AbortController()
    const fetcher = vi.fn(async () => {
      controller.abort()
      return { status: 'running' }
    })
    const onUpdate = vi.fn()
    await poll(fetcher, (v) => isFinished(v.status), onUpdate, { ...quick, signal: controller.signal })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(onUpdate).not.toHaveBeenCalled()
  })

  it('keeps going through a brief loss of connection', async () => {
    const fetcher = vi.fn<() => Promise<{ status: string }>>()
      .mockRejectedValueOnce(new ApiError('network'))
      .mockRejectedValueOnce(new ApiError('network'))
      .mockResolvedValueOnce({ status: 'done' })
    await expect(poll(fetcher, (v) => isFinished(v.status), () => {}, quick)).resolves.toEqual({ status: 'done' })
  })

  it('keeps going through a brief server error', async () => {
    const fetcher = vi.fn<() => Promise<{ status: string }>>()
      .mockRejectedValueOnce(new ApiError('server'))
      .mockResolvedValueOnce({ status: 'done' })
    await expect(poll(fetcher, (v) => isFinished(v.status), () => {}, quick)).resolves.toEqual({ status: 'done' })
  })

  it('gives up after too many connection failures in a row', async () => {
    const fetcher = vi.fn().mockRejectedValue(new ApiError('network'))
    await expect(poll(fetcher, () => false, () => {}, { ...quick, maxTransientErrors: 3 })).rejects.toMatchObject({ code: 'network' })
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('stops immediately on other errors', async () => {
    const fetcher = vi.fn().mockRejectedValue(new ApiError('expired'))
    await expect(poll(fetcher, () => false, () => {}, quick)).rejects.toMatchObject({ code: 'expired' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})

describe('free allowance and limits', () => {
  it('reads who is calling and what is left', async () => {
    const me = { user_id: 'u', free_searches_left: 1, free_tailors_left: 0, unlimited: false, free_max_results: 10 }
    const fetchMock = respondWith(200, me)
    await expect(api.me()).resolves.toEqual(me)
    expect(fetchMock.mock.calls[0][0 as never]).toBe('/api/me')
  })

  it.each([
    [403, 'allowance_used'],
    [403, 'free_limit'],
    [429, 'rate_limited'],
    [429, 'daily_budget'],
  ])('a %i with code %s keeps its code', async (status, code) => {
    respondWith(status, { detail: { code } })
    await expect(api.startSearch({ cv_id: 'c', title: 'QA', country: 'Germany', cities: [], remote: false, max_results: 10 })).rejects.toMatchObject({ code })
  })

  it('an unknown code is a plain server error', async () => {
    respondWith(429, { detail: { code: 'something_else' } })
    await expect(api.getRun('r')).rejects.toMatchObject({ code: 'server' })
  })

  it('a body that is not JSON is still an error with a code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>', { status: 403 })))
    await expect(api.getRun('r')).rejects.toBeInstanceOf(ApiError)
  })
})
