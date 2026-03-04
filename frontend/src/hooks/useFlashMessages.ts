import { useState, useCallback } from 'react';
import type { FlashbarProps } from '@cloudscape-design/components/flashbar';

let nextId = 0;

export function useFlashMessages() {
  const [items, setItems] = useState<FlashbarProps.MessageDefinition[]>([]);

  const addMessage = useCallback(
    (type: 'success' | 'error' | 'warning' | 'info', content: string) => {
      const id = String(nextId++);
      const item: FlashbarProps.MessageDefinition = {
        id,
        type,
        content,
        dismissible: true,
        onDismiss: () => setItems((prev) => prev.filter((i) => i.id !== id)),
      };
      setItems((prev) => [...prev, item]);

      if (type !== 'error') {
        setTimeout(() => {
          setItems((prev) => prev.filter((i) => i.id !== id));
        }, 5000);
      }
    },
    []
  );

  const clearMessages = useCallback(() => setItems([]), []);

  return { items, addMessage, clearMessages };
}
