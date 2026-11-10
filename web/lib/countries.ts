/** Values must match the backend's `Country` list exactly (a pytest contract test checks this). */
export const countries = [
  { value: 'United Arab Emirates', ar: 'الإمارات العربية المتحدة' },
  { value: 'Saudi Arabia', ar: 'المملكة العربية السعودية' },
  { value: 'Qatar', ar: 'قطر' },
  { value: 'Kuwait', ar: 'الكويت' },
  { value: 'Bahrain', ar: 'البحرين' },
  { value: 'Oman', ar: 'عُمان' },
  { value: 'Jordan', ar: 'الأردن' },
  { value: 'Lebanon', ar: 'لبنان' },
  { value: 'Iraq', ar: 'العراق' },
  { value: 'Egypt', ar: 'مصر' },
  { value: 'Germany', ar: 'ألمانيا' },
  { value: 'France', ar: 'فرنسا' },
  { value: 'Netherlands', ar: 'هولندا' },
  { value: 'Belgium', ar: 'بلجيكا' },
  { value: 'Spain', ar: 'إسبانيا' },
  { value: 'Italy', ar: 'إيطاليا' },
  { value: 'Portugal', ar: 'البرتغال' },
  { value: 'Switzerland', ar: 'سويسرا' },
  { value: 'Austria', ar: 'النمسا' },
  { value: 'Ireland', ar: 'أيرلندا' },
  { value: 'Sweden', ar: 'السويد' },
  { value: 'Denmark', ar: 'الدنمارك' },
  { value: 'Norway', ar: 'النرويج' },
  { value: 'Finland', ar: 'فنلندا' },
  { value: 'United Kingdom', ar: 'المملكة المتحدة' },
  { value: 'United States', ar: 'الولايات المتحدة' },
  { value: 'Canada', ar: 'كندا' },
]

/** Suggestions only; users can type any city. The English name is what gets searched. */
export const citySuggestions: Record<string, { en: string; ar: string }[]> = {
  'United Arab Emirates': [
    { en: 'Dubai', ar: 'دبي' },
    { en: 'Abu Dhabi', ar: 'أبوظبي' },
    { en: 'Sharjah', ar: 'الشارقة' },
  ],
  'Saudi Arabia': [
    { en: 'Riyadh', ar: 'الرياض' },
    { en: 'Jeddah', ar: 'جدة' },
  ],
  Qatar: [{ en: 'Doha', ar: 'الدوحة' }],
  Jordan: [{ en: 'Amman', ar: 'عمّان' }],
  Egypt: [
    { en: 'Cairo', ar: 'القاهرة' },
    { en: 'Alexandria', ar: 'الإسكندرية' },
  ],
  'United Kingdom': [
    { en: 'London', ar: 'لندن' },
    { en: 'Manchester', ar: 'مانشستر' },
  ],
}
