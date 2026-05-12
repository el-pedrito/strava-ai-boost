import type { SVGProps } from 'react';

/**
 * Empty state illustration for "not found" / search states.
 * Magnifying glass over an empty document.
 */
export function SearchIllustration({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      {/* Document */}
      <path
        d="M64 32 H 116 L 134 50 V 124 A 4 4 0 0 1 130 128 H 64 A 4 4 0 0 1 60 124 V 36 A 4 4 0 0 1 64 32 Z"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      {/* Folded corner */}
      <path
        d="M116 32 V 50 H 134"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />

      {/* Empty placeholder lines */}
      <line
        x1="72"
        y1="68"
        x2="116"
        y2="68"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <line
        x1="72"
        y1="80"
        x2="124"
        y2="80"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <line
        x1="72"
        y1="92"
        x2="100"
        y2="92"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* Magnifying glass — circle */}
      <circle
        cx="130"
        cy="98"
        r="22"
        stroke="currentColor"
        strokeOpacity="0.75"
        strokeWidth="2"
      />
      {/* Magnifying glass — inner highlight */}
      <path
        d="M118 92 A 12 12 0 0 1 124 86"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      {/* Handle */}
      <line
        x1="146"
        y1="114"
        x2="160"
        y2="128"
        stroke="currentColor"
        strokeOpacity="0.75"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
