import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { render } from '@testing-library/react';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { LoadLineChart } from '../charts';

// jsdom has no layout, so ResponsiveContainer would measure 0 px and draw nothing.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) =>
      isValidElement(children) ? cloneElement(children as ReactElement<{ width: number; height: number }>, { width: 600, height: 200 }) : null,
  };
});

beforeEach(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});

const rows = Array.from({ length: 10 }, (_, i) => ({
  date: `2026-10-${String(10 + i).padStart(2, '0')}`,
  ctl: 20 + i,
  atl: 25 - i,
}));

function renderLoad() {
  return render(
    <ThemeProvider>
      <LoadLineChart data={rows} gaps={[]} ctlName="Forme de fond (CTL)" atlName="Fatigue (ATL)" lang="fr" />
    </ThemeProvider>
  );
}

describe('LoadLineChart', () => {
  it('draws ATL dashed with the AA chart-secondary token', () => {
    const { container } = renderLoad();
    const atl = [...container.querySelectorAll('path.recharts-curve')].find(
      (p) => p.getAttribute('stroke') === 'var(--chart-secondary)'
    );
    expect(atl).toBeDefined();
    expect(atl).toHaveAttribute('stroke-dasharray', '5 3');
  });

  it('lists CTL first in the legend, and the ATL legend text uses the same token', () => {
    const { container } = renderLoad();
    const items = [...container.querySelectorAll('.recharts-legend-item-text')];
    expect(items.map((i) => i.textContent)).toEqual(['Forme de fond (CTL)', 'Fatigue (ATL)']);
    expect((items[1] as HTMLElement).style.color).toBe('var(--chart-secondary)');
  });
});
