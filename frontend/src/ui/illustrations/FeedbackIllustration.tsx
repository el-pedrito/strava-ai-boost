import type { SVGProps } from 'react';

/**
 * Empty state illustration for coach feedback.
 * Speech bubble with abstract text lines and a subtle wisdom star accent.
 */
export function FeedbackIllustration({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      {/* Background ghost bubble */}
      <path
        d="M48 38 H 152 A 12 12 0 0 1 164 50 V 96 A 12 12 0 0 1 152 108 H 90 L 70 124 V 108 H 48 A 12 12 0 0 1 36 96 V 50 A 12 12 0 0 1 48 38 Z"
        stroke="currentColor"
        strokeOpacity="0.2"
        strokeWidth="1.5"
        transform="translate(8 6)"
      />

      {/* Main speech bubble */}
      <path
        d="M48 38 H 152 A 12 12 0 0 1 164 50 V 96 A 12 12 0 0 1 152 108 H 90 L 70 124 V 108 H 48 A 12 12 0 0 1 36 96 V 50 A 12 12 0 0 1 48 38 Z"
        stroke="currentColor"
        strokeOpacity="0.7"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />

      {/* Text lines inside bubble */}
      <line
        x1="54"
        y1="58"
        x2="138"
        y2="58"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <line
        x1="54"
        y1="72"
        x2="146"
        y2="72"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <line
        x1="54"
        y1="86"
        x2="110"
        y2="86"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* Wisdom star (accent) */}
      <path
        d="M156 28 L 158.4 33.2 L 164 34 L 160 38 L 161 43.6 L 156 41 L 151 43.6 L 152 38 L 148 34 L 153.6 33.2 Z"
        stroke="currentColor"
        strokeOpacity="0.5"
        strokeWidth="1.4"
        strokeLinejoin="round"
        fill="currentColor"
        fillOpacity="0.15"
      />
      {/* Tiny secondary star */}
      <path
        d="M174 56 L 175 59 L 178 60 L 175 61 L 174 64 L 173 61 L 170 60 L 173 59 Z"
        stroke="currentColor"
        strokeOpacity="0.35"
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </svg>
  );
}
