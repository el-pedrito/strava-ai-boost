import { useCallback, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { BottomNav } from './BottomNav';
import { MobileDrawer } from './MobileDrawer';
import { FlashToasts } from './FlashToasts';
import { FlashProvider, type AddFlashFn, type FlashItem, type FlashType } from './flash';

let nextFlashId = 0;

export function Shell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [items, setItems] = useState<FlashItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const addFlash: AddFlashFn = useCallback(
    (type: FlashType, content: string) => {
      const id = `flash-${nextFlashId++}`;
      const item: FlashItem = {
        id,
        type,
        content,
        onDismiss: () => dismiss(id),
      };
      setItems((prev) => [...prev, item]);

      if (type !== 'error') {
        window.setTimeout(() => dismiss(id), 5000);
      }
    },
    [dismiss]
  );

  return (
    <FlashProvider value={addFlash}>
      <div className="flex min-h-screen bg-background text-foreground">
        <div className="hidden lg:block">
          <Sidebar />
        </div>

        <MobileDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onMenuClick={() => setDrawerOpen(true)} />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 pb-24 md:px-8 md:py-10 md:pb-10">
            <Outlet />
          </main>
        </div>

        <BottomNav />
        <FlashToasts items={items} />
      </div>
    </FlashProvider>
  );
}
