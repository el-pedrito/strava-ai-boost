import type { SVGProps } from 'react';

/**
 * Empty state illustration for activity lists.
 * Stylised runner silhouette with a minimal GPS trace in the background.
 * Uses currentColor + opacity layers — color via parent text color.
 */
export function ActivityIllustration({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      {/* Background GPS trace */}
      <path
        d="M20 110 C 50 60, 80 130, 110 80 S 170 100, 185 50"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray="3 4"
      />
      {/* GPS pin start */}
      <circle cx="20" cy="110" r="3" fill="currentColor" fillOpacity="0.35" />
      {/* GPS pin end */}
      <circle cx="185" cy="50" r="3" fill="currentColor" fillOpacity="0.35" />

      {/* Soft ground line */}
      <line
        x1="40"
        y1="138"
        x2="160"
        y2="138"
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeWidth="1"
        strokeLinecap="round"
      />

      {/* Runner silhouette — head */}
      <circle cx="104" cy="58" r="7" stroke="currentColor" strokeOpacity="0.7" strokeWidth="1.75" />
      {/* Runner torso */}
      <path
        d="M104 67 L98 95"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      {/* Front arm */}
      <path
        d="M101 75 L114 70 L120 78"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Back arm */}
      <path
        d="M99 76 L88 84 L84 78"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Front leg */}
      <path
        d="M98 95 L112 110 L120 124"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Back leg */}
      <path
        d="M98 95 L86 112 L78 122"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Speed lines accent */}
      <path
        d="M70 70 L78 70 M68 80 L74 80"
        stroke="currentColor"
        strokeOpacity="0.4"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
