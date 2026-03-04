interface Props {
  size?: number;
}

export function AgentCoreLogo({ size = 24 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="5" y="5" width="14" height="14" rx="3" stroke="#7B61FF" strokeWidth="1.5" />
      <circle cx="9" cy="9" r="1.5" fill="#7B61FF" />
      <circle cx="15" cy="9" r="1.5" fill="#7B61FF" />
      <circle cx="9" cy="15" r="1.5" fill="#7B61FF" />
      <circle cx="15" cy="15" r="1.5" fill="#7B61FF" />
      <path d="M9 9h6M9 15h6M9 9v6M15 9v6" stroke="#7B61FF" strokeWidth="0.75" opacity="0.5" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="#7B61FF" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
