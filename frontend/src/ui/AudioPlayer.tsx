import { useEffect, useRef, useState, useCallback } from 'react';
import { Pause, Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '../lib/cn';

export interface AudioPlayerProps {
  src: string;
  /** Optional duration hint in seconds. Used until metadata loads. */
  duration?: number;
  className?: string;
  /** Optional accessible label override (e.g. "Audio debrief"). */
  ariaLabel?: string;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function AudioPlayer({ src, duration, className, ariaLabel }: AudioPlayerProps) {
  const { t } = useTranslation();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [totalDuration, setTotalDuration] = useState<number>(duration ?? 0);

  // Reset internal state whenever the source changes
  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
    setTotalDuration(duration ?? 0);
  }, [src, duration]);

  const togglePlay = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) {
      void el.play();
    } else {
      el.pause();
    }
  }, []);

  const handleScrub = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const el = audioRef.current;
      if (!el) return;
      const next = Number(event.target.value);
      if (Number.isFinite(next)) {
        el.currentTime = next;
        setCurrentTime(next);
      }
    },
    [],
  );

  const handleLoadedMetadata = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    if (Number.isFinite(el.duration) && el.duration > 0) {
      setTotalDuration(el.duration);
    }
  }, []);

  const playLabel = playing ? t('activity.audio.pause') : t('activity.audio.play');
  const ariaLabelValue = ariaLabel ?? t('activity.audio.title');
  const safeDuration = totalDuration > 0 ? totalDuration : duration ?? 0;
  const progressMax = safeDuration > 0 ? safeDuration : 1;

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-lg border border-border bg-surface p-3',
        className,
      )}
      role="group"
      aria-label={ariaLabelValue}
    >
      <button
        type="button"
        onClick={togglePlay}
        aria-label={playLabel}
        aria-pressed={playing}
        className={cn(
          'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full',
          'bg-primary text-primary-foreground transition-all hover:brightness-110',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        )}
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </button>

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <input
          type="range"
          min={0}
          max={progressMax}
          step={0.1}
          value={Math.min(currentTime, progressMax)}
          onChange={handleScrub}
          aria-label={ariaLabelValue}
          className={cn(
            'h-1 w-full cursor-pointer appearance-none rounded-full bg-muted',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            '[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3',
            '[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary',
            '[&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:border-0',
          )}
        />
        <div className="flex items-center justify-between font-numeric text-xs text-muted-foreground">
          <span>{formatTime(currentTime)}</span>
          <span>{formatTime(safeDuration)}</span>
        </div>
      </div>

      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setCurrentTime(0);
        }}
      />
    </div>
  );
}
