import { arSA } from '@clerk/localizations'

/**
 * Clerk's Arabic texts, with the gaps on the sign-in and sign-up path filled in. Clerk's
 * translation is community-made and incomplete (checked 2026-11-10 in @clerk/localizations
 * 4.24.6: about 1,070 of 1,700 texts missing, mostly on screens NextRole doesn't use).
 * Anything not listed here falls back to English.
 */
export const clerkArabic = {
  ...arSA,
  formFieldInputPlaceholder__emailAddress: 'أدخل بريدك الإلكتروني',
  formFieldInputPlaceholder__password: 'أدخل كلمة المرور',
  formFieldInputPlaceholder__signUpPassword: 'أنشئ كلمة مرور',
  unstable__errors: {
    ...arSA.unstable__errors,
    form_password_incorrect: 'كلمة المرور غير صحيحة. حاول مرة أخرى.',
    form_password_length_too_short: 'كلمة المرور قصيرة جدًا.',
    form_password_compromised__sign_in: 'ظهرت كلمة المرور هذه في تسريب بيانات. اختر كلمة مرور أخرى.',
    form_password_untrusted__sign_in: 'لا يمكن استخدام كلمة المرور هذه. اختر كلمة مرور أخرى.',
  },
}
