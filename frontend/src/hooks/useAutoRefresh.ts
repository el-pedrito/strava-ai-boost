import { useEffect, useRef } from 'react';

export function useAutoRefresh(callback: () => void, intervalMs: number = 60000) {
  const callbackRef = useRef(callback);

  // Keep the latest callback without mutating the ref during render, so the
  // interval below never has to be torn down when the callback identity changes.
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;

    const start = () => {
      timer = setInterval(() => callbackRef.current(), intervalMs);
    };

    const handleVisibility = () => {
      clearInterval(timer);
      if (!document.hidden) {
        callbackRef.current();
        start();
      }
    };

    start();
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [intervalMs]);
}
