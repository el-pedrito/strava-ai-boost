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
