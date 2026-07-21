import type { Variants } from 'framer-motion';

/** Parent container: staggers the reveal of its children. */
export const staggerContainer: Variants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.06 },
  },
};

/** Child item: subtle fade + rise, driven by the parent stagger. */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: 'easeOut' },
  },
};
