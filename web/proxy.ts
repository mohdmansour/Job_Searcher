import { clerkMiddleware } from '@clerk/nextjs/server'

// Lets pages read the session. It decides nothing itself: each app page calls auth.protect().
export default clerkMiddleware()

export const config = {
  // Skips /api on purpose: the backend verifies every API request itself, so this layer would
  // add nothing there, and large CV uploads stay out of it.
  matcher: [
    '/((?!_next|api/|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
  ],
}
