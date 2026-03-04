interface Props {
  size?: number;
}

export function CampusCoachLogo({ size = 24 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="12" cy="4" r="2.5" fill="#00B853" />
      <path
        d="M8 9.5C8 8.67 8.67 8 9.5 8h5c.83 0 1.5.67 1.5 1.5V10l-2 3.5 2.5 4.5-2 1-2-3.5L10 19l-2-1 2.5-4.5L8.5 10V9.5z"
        fill="#00B853"
      />
      <path
        d="M6.5 11l2-1M17.5 11l-2-1"
        stroke="#00B853"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
