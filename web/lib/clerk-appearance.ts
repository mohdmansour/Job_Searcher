/**
 * Clerk's sign-in, sign-up and account screens in Candor's own colours and font. Values are the
 * site's CSS variables (app/globals.css), so the two can't drift apart.
 * Source: https://clerk.com/docs/nextjs/guides/customizing-clerk/appearance-prop/variables
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: 'var(--primary)',
    colorPrimaryForeground: 'var(--primary-foreground)',
    colorBackground: 'var(--card)',
    colorForeground: 'var(--foreground)',
    colorMuted: 'var(--muted)',
    colorMutedForeground: 'var(--muted-foreground)',
    colorInput: 'var(--card)',
    colorInputForeground: 'var(--foreground)',
    colorBorder: 'var(--input)',
    colorDanger: 'var(--destructive)',
    colorRing: 'var(--primary)',
    fontFamily: 'var(--font-sans)',
    borderRadius: 'var(--radius)',
  },
  options: {
    socialButtonsVariant: 'blockButton',
  },
} as const
