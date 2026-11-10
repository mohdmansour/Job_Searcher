import { auth } from '@clerk/nextjs/server'

/**
 * The server-side check at the top of every app page. The browser's own sign-in state only
 * decides what to show; this decides who gets the page. The backend checks every API call too.
 *
 * Upload & search is where new visitors arrive from the landing page, so it sends them to
 * sign-up; the other pages send returning users to sign-in. Both come back to the same page.
 * Source: https://clerk.com/docs/reference/nextjs/app-router/auth
 */
export async function requireAccount(path: string, via: 'sign-in' | 'sign-up' = 'sign-in'): Promise<void> {
  const { isAuthenticated, redirectToSignIn, redirectToSignUp } = await auth()
  if (isAuthenticated) return
  if (via === 'sign-up') redirectToSignUp({ returnBackUrl: path })
  else redirectToSignIn({ returnBackUrl: path })
}
