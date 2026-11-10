import { SignUp } from '@clerk/nextjs'

// Clerk's own form in Candor's colours (lib/clerk-appearance.ts) and language (app/layout.tsx).
export default function Page() {
  return (
    <div className="flex justify-center px-4 py-10 sm:py-16">
      <SignUp />
    </div>
  )
}
