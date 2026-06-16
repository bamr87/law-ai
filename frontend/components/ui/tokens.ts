/**
 * Semantic tone tokens — the single place where a status/category maps to
 * concrete colors. Every Badge/Pill/StatTile/accent in the app reads from here
 * instead of hard-coding `bg-emerald-500/15 ...` strings per component (the
 * audit found 5+ duplicate tone maps).
 */

export type Tone =
  | 'brand'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'accent'
  | 'neutral'

/** Soft "chip" treatment: tinted bg + ring + readable text. */
export const toneChip: Record<Tone, string> = {
  brand: 'bg-brand/15 text-brand ring-brand/30',
  success: 'bg-success/15 text-success ring-success/30',
  warning: 'bg-warning/15 text-warning ring-warning/30',
  danger: 'bg-danger/15 text-danger ring-danger/30',
  info: 'bg-info/15 text-info ring-info/30',
  accent: 'bg-accent/15 text-accent ring-accent/30',
  neutral: 'bg-surface-3 text-muted ring-border',
}

/** Just the dot/indicator color for a tone. */
export const toneDot: Record<Tone, string> = {
  brand: 'bg-brand',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  accent: 'bg-accent',
  neutral: 'bg-subtle',
}

/** Gradient wash used behind KPI/stat tiles. */
export const toneWash: Record<Tone, string> = {
  brand: 'from-brand/15',
  success: 'from-success/15',
  warning: 'from-warning/15',
  danger: 'from-danger/15',
  info: 'from-info/15',
  accent: 'from-accent/15',
  neutral: 'from-surface-3/40',
}
