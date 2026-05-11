import { createContext, useContext } from 'react';

export type FlashType = 'success' | 'error' | 'warning' | 'info';

export interface FlashItem {
  id: string;
  type: FlashType;
  content: string;
  onDismiss: () => void;
}

export type AddFlashFn = (type: FlashType, content: string) => void;

const FlashContext = createContext<AddFlashFn>(() => {});

export const FlashProvider = FlashContext.Provider;

export function useFlash(): AddFlashFn {
  return useContext(FlashContext);
}
