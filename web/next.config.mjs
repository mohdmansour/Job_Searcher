// The site sends no data to third parties, and that includes Next.js's own usage telemetry.
process.env.NEXT_TELEMETRY_DISABLED = '1'
process.env.CLERK_TELEMETRY_DISABLED = '1'

// Clerk's sign-in service for this app. A production instance will use its own domain.
const CLERK_HOST = process.env.CLERK_FRONTEND_HOST ?? 'https://*.clerk.accounts.dev'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

// Only what the site uses. Everything else on the backend (such as /docs) stays private.
const API_ROUTES = ['/me', '/me/data', '/cv', '/cv/:id', '/estimate/search', '/estimate/tailor', '/search', '/runs/:id', '/tailor', '/tailor/:id', '/files/:tailorId/:name']

const SECURITY_HEADERS = [
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'no-referrer' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
]
// Development needs eval and websockets, so the policy applies to production builds only.
if (process.env.NODE_ENV === 'production') {
  SECURITY_HEADERS.push({
    key: 'Content-Security-Policy',
    value: [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline' ${CLERK_HOST} https://challenges.cloudflare.com https://*.protect.clerk.com`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https://img.clerk.com",
      "font-src 'self' data:",
      `connect-src 'self' ${CLERK_HOST} https://*.protect.clerk.com:*`,
      "worker-src 'self' blob:",
      'frame-src https://challenges.cloudflare.com https://*.protect.clerk.com',
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; '),
  })
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  agentRules: false,
  env: {
    NEXT_PUBLIC_CLERK_TELEMETRY_DISABLED: '1',
    NEXT_PUBLIC_CLERK_SIGN_IN_URL: '/sign-in',
    NEXT_PUBLIC_CLERK_SIGN_UP_URL: '/sign-up',
    NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL: '/search',
    NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL: '/search',
  },
  poweredByHeader: false,
  devIndicators: false,
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: import.meta.dirname,
  },
  experimental: {
    // POST /cv blocks while the CV is read (OCR + model); the default limit is 30 s.
    proxyTimeout: 300_000,
    // The backend accepts PDFs up to 10 MB; the multipart wrapper adds a little on top.
    proxyClientMaxBodySize: '12mb',
  },
  async rewrites() {
    return API_ROUTES.map((route) => ({ source: `/api${route}`, destination: `${BACKEND_URL}${route}` }))
  },
  async headers() {
    return [{ source: '/:path*', headers: SECURITY_HEADERS }]
  },
}

export default nextConfig
