interface Props {
  size?: number;
}

export function EndurawLogo({ size = 24 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M3 12c2-3 4-4.5 6-4.5s3 1.5 3 1.5 1-1.5 3-1.5 4 1.5 6 4.5"
        stroke="#0073E6"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M3 16c2-3 4-4.5 6-4.5s3 1.5 3 1.5 1-1.5 3-1.5 4 1.5 6 4.5"
        stroke="#0073E6"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.5"
      />
      <circle cx="18" cy="6" r="2" fill="#0073E6" />
      <path d="M18 8v2" stroke="#0073E6" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M16.5 6.5L15 5.5" stroke="#0073E6" strokeWidth="1" strokeLinecap="round" />
      <path d="M19.5 6.5L21 5.5" stroke="#0073E6" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}
