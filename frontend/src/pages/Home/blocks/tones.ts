/** Status text colours for the Home cards (AA in both themes). */

/**
 * Small brand-tinted text. Brand orange fails AA as small text on white
 * (3.40:1) and --primary-strong fails on the dark surface, and there is no
 * theme-aware primary text token, so small "primary" text uses the foreground
 * colour on a primary tint. Large text (>= 24 px) may use `text-primary`
 * (3.40:1 light, 5.07:1 dark, AA for large text).
 */
export const PRIMARY_TEXT = 'text-foreground';

export type Tone = 'success' | 'warning' | 'danger' | 'primary' | 'muted' | 'info';

export const TONE_TEXT: Record<Tone, string> = {
  success: 'text-success-text',
  warning: 'text-warning-text',
  danger: 'text-danger',
  primary: PRIMARY_TEXT,
  muted: 'text-muted-foreground',
  info: 'text-info',
};

/** A larger hit area (44 px) around the 20 px InfoTooltip trigger. */
export const INFO_HIT = "relative before:absolute before:-inset-3 before:content-['']";
