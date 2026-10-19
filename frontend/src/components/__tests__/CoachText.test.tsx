import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CoachText } from '../CoachText';

describe('CoachText', () => {
  it('renders **x** as <strong> and keeps the rest as plain text', () => {
    render(<CoachText text="Reste **vraiment** facile." />);
    const p = screen.getByTestId('coach-text');
    expect(p).toHaveTextContent('Reste vraiment facile.');
    expect(screen.getByText('vraiment').tagName).toBe('STRONG');
    expect(p.textContent).not.toContain('**');
  });

  it('turns a video URL into a "the video" link opened safely in a new tab', () => {
    render(<CoachText text="Regarde https://www.youtube.com/watch?v=abc123. Bonne séance" />);
    const link = screen.getByRole('link', { name: 'the video' });
    expect(link).toHaveAttribute('href', 'https://www.youtube.com/watch?v=abc123');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    // The trailing period stays as text, outside the link.
    expect(screen.getByTestId('coach-text')).toHaveTextContent('Regarde the video. Bonne séance');
  });

  it('labels a non-video URL "the link" and keeps a closing parenthesis as text', () => {
    render(<CoachText text="(voir https://example.org/guide)" />);
    expect(screen.getByRole('link', { name: 'the link' })).toHaveAttribute('href', 'https://example.org/guide');
    expect(screen.getByTestId('coach-text')).toHaveTextContent('(voir the link)');
  });

  it('keeps a link inside bold text bold, with no stray **', () => {
    render(<CoachText text="**Regarde https://youtu.be/xyz789** avant la séance." />);
    const link = screen.getByRole('link', { name: 'the video' });
    expect(link).toHaveAttribute('href', 'https://youtu.be/xyz789');
    expect(link.closest('strong')).not.toBeNull();
    const p = screen.getByTestId('coach-text');
    expect(p.textContent).not.toContain('**');
    expect(p).toHaveTextContent('Regarde the video avant la séance.');
  });

  it('never interprets HTML in the text', () => {
    const { container } = render(<CoachText text={'<img src=x onerror="alert(1)"> <b>gras</b>'} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(screen.getByTestId('coach-text')).toHaveTextContent('<img src=x onerror="alert(1)"> <b>gras</b>');
  });

  it('does not link a javascript: pseudo-URL', () => {
    render(<CoachText text="javascript:alert(1)" />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('clamps to the given number of lines, and shows no toggle when nothing overflows', () => {
    render(<CoachText text="Court." clampLines={3} />);
    const p = screen.getByTestId('coach-text');
    expect(p.style.webkitLineClamp).toBe('3');
    // jsdom has no layout, so nothing is measured as overflowing.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('does not clamp without clampLines', () => {
    render(<CoachText text="Texte libre." />);
    expect(screen.getByTestId('coach-text').style.webkitLineClamp).toBe('');
  });
});
