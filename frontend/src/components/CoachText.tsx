import { useCallback, useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/cn';

/**
 * Raw Campus text (coach word, session instructions) rendered as plain text.
 *
 * Only two pieces of markup are understood: `**x**` becomes <strong>, and an
 * http(s) URL becomes a short link ("la vidéo" for a video host, "le lien"
 * otherwise) opened in a new tab. Everything else is a text node: the text comes
 * from a third party, so it never goes through `dangerouslySetInnerHTML`.
 */
export interface CoachTextProps {
  text: string;
  /** Clamp to this many lines with a "read more" toggle when the text overflows. */
  clampLines?: number;
  className?: string;
}

// Parentheses are excluded so "(voir ici : https://x)" keeps its closing paren as text.
const URL_RE = /https?:\/\/[^\s<>"'()]+/g;
const TRAILING_PUNCT_RE = /[.,;:!?]+$/;
const BOLD_RE = /\*\*([^*]+?)\*\*/g;
const VIDEO_HOSTS = ['youtube.com', 'youtu.be', 'vimeo.com'];

type Segment = { kind: 'text'; value: string } | { kind: 'url'; value: string };

/** Split a text into text and URL segments. */
function splitUrls(text: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(URL_RE)) {
    const start = match.index ?? 0;
    let url = match[0];
    const trailing = TRAILING_PUNCT_RE.exec(url)?.[0] ?? '';
    url = url.slice(0, url.length - trailing.length);
    if (start > last) segments.push({ kind: 'text', value: text.slice(last, start) });
    if (url.length > 'https://'.length) segments.push({ kind: 'url', value: url });
    else segments.push({ kind: 'text', value: url });
    last = start + url.length;
  }
  if (last < text.length) segments.push({ kind: 'text', value: text.slice(last) });
  return segments;
}

function isVideoUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return VIDEO_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
  } catch {
    return false;
  }
}

/** Split a text into plain and `**bold**` chunks. Unpaired `**` stay as text. */
function splitBold(text: string): Array<{ bold: boolean; value: string }> {
  const chunks: Array<{ bold: boolean; value: string }> = [];
  let last = 0;
  for (const match of text.matchAll(BOLD_RE)) {
    const start = match.index ?? 0;
    if (start > last) chunks.push({ bold: false, value: text.slice(last, start) });
    chunks.push({ bold: true, value: match[1] });
    last = start + match[0].length;
  }
  if (last < text.length) chunks.push({ bold: false, value: text.slice(last) });
  return chunks;
}

export function CoachText({ text, clampLines, className }: CoachTextProps) {
  const { t } = useTranslation();
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const clamped = typeof clampLines === 'number' && clampLines > 0 && !expanded;

  // Overflow is measured, not guessed from the length: the toggle only shows when
  // the clamp actually hides something at the current width.
  const measureRef = useCallback(
    (el: HTMLParagraphElement | null) => {
      if (!el || !clampLines || typeof ResizeObserver === 'undefined') return;
      const observer = new ResizeObserver(() => {
        setOverflowing(el.scrollHeight > el.clientHeight + 1);
      });
      observer.observe(el);
      return () => observer.disconnect();
    },
    [clampLines]
  );

  // Bold first, then URLs inside each chunk: `**voir https://x**` stays bold with its
  // link, instead of the URL split leaving two stray `**` around it.
  const inline = (value: string, key: string): ReactNode[] =>
    splitUrls(value).map((segment, i) =>
      segment.kind === 'text' ? (
        segment.value
      ) : (
        <a
          key={`${key}-a${i}`}
          href={segment.value}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-primary-text underline underline-offset-2 hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
        >
          {isVideoUrl(segment.value) ? t('coachText.video') : t('coachText.link')}
        </a>
      )
    );
  const nodes: ReactNode[] = splitBold(text).flatMap((chunk, i): ReactNode[] =>
    chunk.bold
      ? [
          <strong key={`c${i}`} className="font-semibold text-foreground">
            {inline(chunk.value, `c${i}`)}
          </strong>,
        ]
      : inline(chunk.value, `c${i}`)
  );

  return (
    <div className={cn('flex flex-col items-start gap-1', className)}>
      <p
        id={id}
        ref={clampLines ? measureRef : undefined}
        data-testid="coach-text"
        className="whitespace-pre-line break-words text-sm leading-relaxed text-foreground"
        style={
          clamped
            ? {
                display: '-webkit-box',
                WebkitLineClamp: clampLines,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }
            : undefined
        }
      >
        {nodes}
      </p>
      {clampLines && (overflowing || expanded) ? (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={() => setExpanded((v) => !v)}
          className="min-h-11 rounded-sm text-sm font-medium text-primary-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {expanded ? t('coachText.less') : t('coachText.more')}
        </button>
      ) : null}
    </div>
  );
}
