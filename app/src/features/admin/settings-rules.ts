/**
 * The bounds the API enforces, repeated here so a wrong number is answered while typing instead
 * of by a 422. The server stays the authority; this only saves the round trip.
 */
export const LIMITS = {
  thumbnail_size: { min: 100, max: 1000 },
  preview_size: { min: 800, max: 8000 },
  image_quality: { min: 50, max: 100 },
  video_height: { min: 360, max: 2160 },

  quick_sync_seconds: { min: 60, max: 3600 },
  full_sync_hour: { min: 0, max: 23 },
  stability_seconds: { min: 5, max: 600 },
  missing_grace_days: { min: 0, max: 365 },
  // The pause before many deletions at once. 0 is off, which is the default.
  deletion_share_percent: { min: 0, max: 50 },
  deletion_count: { min: 0, max: 100000 },
} as const

export type NumericSetting = keyof typeof LIMITS

/** Which fields belong together on the page, in the order they are shown. */
export const DERIVATIVE_SETTINGS = [
  'thumbnail_size',
  'preview_size',
  'image_quality',
  'video_height',
] as const satisfies readonly NumericSetting[]

export const SYNC_SETTINGS = [
  'quick_sync_seconds',
  'full_sync_hour',
  'stability_seconds',
  'missing_grace_days',
  'deletion_share_percent',
  'deletion_count',
] as const satisfies readonly NumericSetting[]

export interface SettingsProblem {
  /** The setting that is out of bounds; the page looks up its message and label. */
  setting: NumericSetting
  params: { min: number; max: number }
}

export function settingsProblem(
  values: Record<NumericSetting, number>,
): SettingsProblem | 'previewTooSmall' | null {
  for (const setting of Object.keys(LIMITS) as NumericSetting[]) {
    const { min, max } = LIMITS[setting]
    const value = values[setting]
    if (!Number.isInteger(value) || value < min || value > max) {
      return { setting, params: { min, max } }
    }
  }

  if (values.preview_size <= values.thumbnail_size) return 'previewTooSmall'

  return null
}

/** A name of one folder or file, never a path. The scanner compares it to a single entry. */
export function isValidIgnoredName(name: string): boolean {
  const trimmed = name.trim()
  return (
    trimmed.length > 0 && trimmed.length <= 100 && !trimmed.includes('/') && !trimmed.includes('\\')
  )
}
