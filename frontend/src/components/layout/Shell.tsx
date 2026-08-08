import { useCallback, useEffect, useRef, useState } from 'react';
import { Outlet } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { BottomNav } from './BottomNav';
import { MobileDrawer } from './MobileDrawer';
import { FlashToasts } from './FlashToasts';
import { FlashProvider, type AddFlashFn, type FlashItem, type FlashType } from './flash';
import { PageTransition } from '../PageTransition';

let nextFlashId = 0;

const SIDEBAR_WIDTH_KEY = 'sab.sidebar.width';
const SIDEBAR_COLLAPSED_KEY = 'sab.sidebar.collapsed';
const MIN_WIDTH = 200;
const MAX_WIDTH = 420;
const DEFAULT_WIDTH = 256;
const COLLAPSED_WIDTH = 64;

function clampWidth(value: number): number {
  return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, value));
}

export function Shell() {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [items, setItems] = useState<FlashItem[]>([]);

  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return DEFAULT_WIDTH;
    const stored = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
    const parsed = stored ? Number(stored) : NaN;
    return Number.isFinite(parsed) ? clampWidth(parsed) : DEFAULT_WIDTH;
  });
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  });
  const [dragging, setDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; width: number } | null>(null);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
    }
  }, [sidebarWidth]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
    }
  }, [collapsed]);

  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e: MouseEvent) => {
      if (!dragStartRef.current) return;
      const delta = e.clientX - dragStartRef.current.x;
      setSidebarWidth(clampWidth(dragStartRef.current.width + delta));
    };
    const handleUp = () => {
      setDragging(false);
      dragStartRef.current = null;
    };
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [dragging]);

  const onResizeStart = (e: React.MouseEvent) => {
    if (collapsed) return;
    dragStartRef.current = { x: e.clientX, width: sidebarWidth };
    setDragging(true);
  };

  const onResizeKey = (e: React.KeyboardEvent) => {
    if (collapsed) return;
    if (e.key === 'ArrowLeft') {
      setSidebarWidth((w) => clampWidth(w - 16));
    } else if (e.key === 'ArrowRight') {
      setSidebarWidth((w) => clampWidth(w + 16));
    }
  };

  const onDoubleClickHandle = () => {
    setSidebarWidth(DEFAULT_WIDTH);
  };

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

  const effectiveWidth = collapsed ? COLLAPSED_WIDTH : sidebarWidth;

  return (
    <FlashProvider value={addFlash}>
      <div className="flex min-h-screen bg-background text-foreground">
        <div className="hidden lg:flex relative">
          <Sidebar
            collapsed={collapsed}
            width={effectiveWidth}
            onToggleCollapse={() => setCollapsed((v) => !v)}
          />
          {!collapsed && (
            <button
              type="button"
              role="separator"
              aria-orientation="vertical"
              aria-label={t('sidebar.resize')}
              tabIndex={0}
              onMouseDown={onResizeStart}
              onKeyDown={onResizeKey}
              onDoubleClick={onDoubleClickHandle}
              className="absolute right-0 top-0 z-20 h-full w-1 -translate-x-1/2 cursor-col-resize bg-transparent transition-colors hover:bg-primary/40 focus-visible:bg-primary/60 focus-visible:outline-none"
            />
          )}
        </div>

        <MobileDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onMenuClick={() => setDrawerOpen(true)} />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 pb-24 md:px-8 md:py-10 md:pb-10">
            <PageTransition>
              <Outlet />
            </PageTransition>
          </main>
        </div>

        <BottomNav />
        <FlashToasts items={items} />
      </div>
    </FlashProvider>
  );
}
