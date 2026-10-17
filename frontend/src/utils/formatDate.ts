export function formatDateTime(isoString: string): string {
  try {
    const dt = new Date(isoString);
    return dt.toISOString().slice(0, 16).replace('T', ' ');
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

/** An ISO 8601 instant as a local "HH:MM", or null when absent or unreadable. */
export function formatLocalTime(isoString: string | undefined): string | null {
  if (!isoString) return null;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return null;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
