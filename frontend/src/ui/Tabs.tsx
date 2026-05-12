import { forwardRef, type ComponentPropsWithoutRef, type ComponentRef } from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cn } from '@/lib/cn';

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef<
  ComponentRef<typeof TabsPrimitive.List>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      'border-b border-border flex gap-1 overflow-x-auto',
      className
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

export const TabsTrigger = forwardRef<
  ComponentRef<typeof TabsPrimitive.Trigger>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'group relative text-sm font-medium px-4 py-3 text-muted-foreground hover:text-foreground transition-colors',
      'data-[state=active]:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-t-md',
      'whitespace-nowrap',
      className
    )}
    {...props}
  >
    {children}
    <span
      aria-hidden="true"
      className={cn(
        'absolute left-2 right-2 -bottom-px h-0.5 rounded-full bg-transparent',
        'transition-all duration-200 ease-out',
        'group-data-[state=active]:bg-primary'
      )}
    />
  </TabsPrimitive.Trigger>
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = forwardRef<
  ComponentRef<typeof TabsPrimitive.Content>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      'pt-6 focus-visible:outline-none',
      'data-[state=active]:animate-fade-in',
      className
    )}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;
