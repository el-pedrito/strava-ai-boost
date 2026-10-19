import { useCallback, useSyncExternalStore } from 'react';

/** True while `query` matches. False where `matchMedia` does not exist (tests, SSR). */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener?.('change', onChange);
      return () => mql.removeEventListener?.('change', onChange);
    },
    [query],
  );
  const getSnapshot = () =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false;
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
