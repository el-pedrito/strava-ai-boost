import type { SVGProps } from 'react';

/**
 * Empty state illustration for celebratory moments — onboarding done, milestone reached.
 * Minimal confetti and a subtle rosette accent.
 */
export function CelebrateIllustration({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      {/* Rosette (central accent) */}
      <circle
        cx="100"
        cy="78"
        r="20"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
      />
      <circle
        cx="100"
        cy="78"
        r="10"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.5"
        fill="currentColor"
        fillOpacity="0.12"
      />
      {/* Rosette ribbons */}
      <path
        d="M88 96 L 84 118 L 92 112 L 96 124 L 100 102"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M112 96 L 116 118 L 108 112 L 104 124 L 100 102"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Confetti — top-left cluster */}
      <line
        x1="36"
        y1="36"
        x2="44"
        y2="42"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <line
        x1="50"
        y1="28"
        x2="50"
        y2="38"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="64" cy="40" r="2.5" fill="currentColor" fillOpacity="0.45" />

      {/* Confetti — top-right cluster */}
      <line
        x1="160"
        y1="32"
        x2="156"
        y2="42"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M170 50 L 174 48 L 172 52 L 176 50"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="148" cy="56" r="2.5" fill="currentColor" fillOpacity="0.45" />

      {/* Confetti — sides */}
      <line
        x1="28"
        y1="84"
        x2="36"
        y2="80"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <line
        x1="172"
        y1="92"
        x2="164"
        y2="88"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* Star accent */}
      <path
        d="M40 110 L 42 114 L 46 114.6 L 43 117 L 44 121 L 40 119 L 36 121 L 37 117 L 34 114.6 L 38 114 Z"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.4"
        strokeLinejoin="round"
        fill="currentColor"
        fillOpacity="0.15"
      />
      <path
        d="M160 116 L 162 120 L 166 120.6 L 163 123 L 164 127 L 160 125 L 156 127 L 157 123 L 154 120.6 L 158 120 Z"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.4"
        strokeLinejoin="round"
        fill="currentColor"
        fillOpacity="0.15"
      />
    </svg>
  );
}
