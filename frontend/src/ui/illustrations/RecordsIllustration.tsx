import type { SVGProps } from 'react';

/**
 * Empty state illustration for personal records.
 * Minimal trophy with a small chrono accent.
 */
export function RecordsIllustration({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 200 160"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      role="img"
      fill="none"
      {...props}
    >
      {/* Trophy cup */}
      <path
        d="M76 38 H 124 V 70 A 24 24 0 0 1 100 94 A 24 24 0 0 1 76 70 Z"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />

      {/* Left handle */}
      <path
        d="M76 46 H 64 A 8 8 0 0 0 56 54 V 60 A 12 12 0 0 0 68 72 H 76"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Right handle */}
      <path
        d="M124 46 H 136 A 8 8 0 0 1 144 54 V 60 A 12 12 0 0 1 132 72 H 124"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Trophy stem */}
      <line
        x1="100"
        y1="94"
        x2="100"
        y2="112"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      {/* Trophy base */}
      <path
        d="M82 124 H 118 L 114 112 H 86 Z"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />

      {/* Star inside cup */}
      <path
        d="M100 56 L 102.6 62 L 109 62.6 L 104 67 L 105.6 73.6 L 100 70 L 94.4 73.6 L 96 67 L 91 62.6 L 97.4 62 Z"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.4"
        strokeLinejoin="round"
        fill="currentColor"
        fillOpacity="0.15"
      />

      {/* Chrono — circle */}
      <circle
        cx="160"
        cy="44"
        r="12"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.5"
      />
      {/* Chrono — top button */}
      <line
        x1="160"
        y1="28"
        x2="160"
        y2="32"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      {/* Chrono — needle */}
      <line
        x1="160"
        y1="44"
        x2="166"
        y2="38"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.5"
        strokeLinecap="round"
      />

      {/* Soft ground line */}
      <line
        x1="60"
        y1="134"
        x2="140"
        y2="134"
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeWidth="1"
        strokeLinecap="round"
      />
    </svg>
  );
}
