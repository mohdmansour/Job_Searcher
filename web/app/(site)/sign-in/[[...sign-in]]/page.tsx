import { SignIn } from '@clerk/nextjs'

// Clerk's own form in NextRole's colours (lib/clerk-appearance.ts) and language (app/layout.tsx).
export default function Page() {
  return (
    <div className="flex justify-center px-4 py-10 sm:py-16">
      <SignIn />
    </div>
  )
}
