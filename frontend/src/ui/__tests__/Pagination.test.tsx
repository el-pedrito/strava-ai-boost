import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Pagination } from '../Pagination';

// jsdom has no layout, so the phone fit (M10, 24 px overflow at 375 px) is pinned through the
// responsive classes: below `sm` the first/last buttons and the page-size select are hidden.
function renderPagination(onPageChange = vi.fn()) {
  render(
    <Pagination
      total={50}
      page={2}
      pageSize={10}
      onPageChange={onPageChange}
      onPageSizeChange={vi.fn()}
    />,
  );
  return onPageChange;
}

describe('Pagination on phones', () => {
  it('hides first/last buttons below sm and shows them from sm', () => {
    renderPagination();
    for (const name of ['First page', 'Last page']) {
      const btn = screen.getByRole('button', { name });
      expect(btn.className.split(' ')).toContain('hidden');
      expect(btn.className.split(' ')).toContain('sm:inline-flex');
    }
  });

  it('keeps previous/next always visible', () => {
    const onPageChange = renderPagination();
    const prev = screen.getByRole('button', { name: 'Previous page' });
    const next = screen.getByRole('button', { name: 'Next page' });
    expect(prev.className.split(' ')).not.toContain('hidden');
    expect(next.className.split(' ')).not.toContain('hidden');
    fireEvent.click(next);
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it('hides the page-size select below sm and lets the controls wrap', () => {
    renderPagination();
    const pageSize = screen.getByTestId('pagination-page-size');
    expect(pageSize.className.split(' ')).toEqual(expect.arrayContaining(['hidden', 'sm:flex']));
    expect(pageSize.parentElement?.className.split(' ')).toContain('flex-wrap');
  });
});
