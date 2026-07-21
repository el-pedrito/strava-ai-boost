import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KPI } from '../KPI';

describe('KPI delta unit', () => {
  it('suffixes % by default on an integer delta', () => {
    render(<KPI label="Volume" value="12 km" delta={{ value: 3 }} />);
    expect(screen.getByText('+3%')).toBeInTheDocument();
  });

  it('suffixes % by default on a decimal delta (regression: heuristic dropped the unit)', () => {
    render(<KPI label="Volume" value="12 km" delta={{ value: 2.5 }} />);
    expect(screen.getByText('+2.5%')).toBeInTheDocument();
  });

  it('uses a custom deltaUnit when provided', () => {
    render(<KPI label="Charge" value="480" delta={{ value: -1.5 }} deltaUnit="pts" />);
    expect(screen.getByText('-1.5pts')).toBeInTheDocument();
  });

  it('renders a unitless delta with an empty deltaUnit', () => {
    render(<KPI label="Sessions" value="4" delta={{ value: 1 }} deltaUnit="" />);
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('renders the delta label alongside the value', () => {
    render(<KPI label="Volume" value="12 km" delta={{ value: 3, label: 'vs last week' }} />);
    expect(screen.getByText('+3%')).toBeInTheDocument();
    expect(screen.getByText('vs last week')).toBeInTheDocument();
  });
});
