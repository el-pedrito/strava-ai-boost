import i18n from '../i18n';

/** The athlete lives in Paris: every timestamp is shown in that zone, whatever the device says. */
export const DISPLAY_TIME_ZONE = 'Europe/Paris';

function intlLocale(lang?: string): string {
  const base = (lang ?? i18n.language ?? 'fr').split('-')[0];
  // en-GB keeps the 24 h clock and "Fri 16 Oct" order, closer to the French form than en-US.
  return base === 'en' ? 'en-GB' : 'fr-FR';
}

/**
 * ISO timestamp → short local form in Europe/Paris, e.g. "ven. 16 oct., 17:50".
 * The locale follows the current i18n language unless `lang` is given.
 * Returns 'N/A' for an empty or unparseable value.
 */
export function formatDateTime(isoString: string, lang?: string): string {
  if (!isoString) return 'N/A';
  const dt = new Date(isoString);
  if (Number.isNaN(dt.getTime())) return 'N/A';
  try {
    return new Intl.DateTimeFormat(intlLocale(lang), {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: DISPLAY_TIME_ZONE,
    }).format(dt);
  } catch {
    return 'N/A';
  }
}

export function computeProcessingTime(createdAt?: string, updatedAt?: string): string {
  if (!createdAt || !updatedAt) return 'N/A';
  try {
    const created = new Date(createdAt);
    const updated = new Date(updatedAt);
    return `${Math.round((updated.getTime() - created.getTime()) / 1000)}s`;
  } catch {
    return 'N/A';
  }
}
