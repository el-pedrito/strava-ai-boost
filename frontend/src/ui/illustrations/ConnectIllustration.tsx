import type { SVGProps } from 'react';

/**
 * Empty state illustration for "connect Strava" / setup pending.
 * Two nodes joined by an animated-looking dashed link.
 */
export function ConnectIllustration({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      {/* Left node — outer ring */}
      <circle
        cx="56"
        cy="80"
        r="22"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
      />
      {/* Left node — inner */}
      <circle
        cx="56"
        cy="80"
        r="8"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.5"
        fill="currentColor"
        fillOpacity="0.12"
      />

      {/* Right node — outer ring */}
      <circle
        cx="144"
        cy="80"
        r="22"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
      />
      {/* Right node — inner */}
      <circle
        cx="144"
        cy="80"
        r="8"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.5"
        fill="currentColor"
        fillOpacity="0.12"
      />

      {/* Connection line (dashed) */}
      <line
        x1="78"
        y1="80"
        x2="122"
        y2="80"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="3 5"
      />

      {/* Pulse arrow at midpoint */}
      <path
        d="M96 74 L 104 80 L 96 86"
        stroke="currentColor"
        strokeOpacity="0.65"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Subtle node halos */}
      <circle
        cx="56"
        cy="80"
        r="32"
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeWidth="1"
        strokeDasharray="2 4"
      />
      <circle
        cx="144"
        cy="80"
        r="32"
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeWidth="1"
        strokeDasharray="2 4"
      />
    </svg>
  );
}
