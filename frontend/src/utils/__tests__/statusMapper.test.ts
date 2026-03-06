import { describe, it, expect } from 'vitest';
import {
  statusType,
  agentcoreType,
  agentcoreLabel,
  formatModuleName,
  getActivityIcon,
  ACTIVITY_TYPE_ICONS,
} from '../statusMapper';

describe('statusType', () => {
  it('maps completed to success', () => {
    expect(statusType('completed')).toBe('success');
  });

  it('maps processing to in-progress', () => {
    expect(statusType('processing')).toBe('in-progress');
  });

  it('maps error to error', () => {
    expect(statusType('error')).toBe('error');
  });

  it('defaults to info for unknown status', () => {
    expect(statusType('pending')).toBe('info');
    expect(statusType('')).toBe('info');
  });
});

describe('agentcoreType', () => {
  it('maps healthy to success', () => {
    expect(agentcoreType('healthy')).toBe('success');
  });

  it('maps not_configured to warning', () => {
    expect(agentcoreType('not_configured')).toBe('warning');
  });

  it('defaults to error for unknown', () => {
    expect(agentcoreType('down')).toBe('error');
    expect(agentcoreType('')).toBe('error');
  });
});

describe('agentcoreLabel', () => {
  it('replaces underscores and capitalizes words', () => {
    expect(agentcoreLabel('not_configured')).toBe('Not Configured');
  });

  it('capitalizes single word', () => {
    expect(agentcoreLabel('healthy')).toBe('Healthy');
  });

  it('handles empty string', () => {
    expect(agentcoreLabel('')).toBe('');
  });
});

describe('formatModuleName', () => {
  it('recognizes campus_coach', () => {
    const result = formatModuleName('campus_coach');
    expect(result.label).toBe('Campus Coach');
    expect(result.className).toBe('badge-campus');
  });

  it('recognizes campus by substring', () => {
    const result = formatModuleName('my_campus_module');
    expect(result.label).toBe('Campus Coach');
    expect(result.className).toBe('badge-campus');
  });

  it('recognizes enduraw', () => {
    const result = formatModuleName('enduraw');
    expect(result.label).toBe('Enduraw');
    expect(result.className).toBe('badge-enduraw');
  });

  it('returns raw name for unknown modules', () => {
    const result = formatModuleName('custom_module');
    expect(result.label).toBe('custom_module');
    expect(result.className).toBe('');
  });
});

describe('getActivityIcon', () => {
  it('returns icon for known types', () => {
    expect(getActivityIcon('Run')).toBe(ACTIVITY_TYPE_ICONS['Run']);
    expect(getActivityIcon('Ride')).toBe(ACTIVITY_TYPE_ICONS['Ride']);
    expect(getActivityIcon('Swim')).toBe(ACTIVITY_TYPE_ICONS['Swim']);
  });

  it('returns empty string for unknown type', () => {
    expect(getActivityIcon('Surfing')).toBe('');
  });

  it('returns empty string for undefined', () => {
    expect(getActivityIcon(undefined)).toBe('');
  });

  it('returns empty string for empty string', () => {
    expect(getActivityIcon('')).toBe('');
  });
});
