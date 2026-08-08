const BRAND_NAME = "TrackYourFinances";

type BrandLogoProps = {
  size?: "sm" | "md" | "lg";
  showWordmark?: boolean;
};

const MARK_PX: Record<NonNullable<BrandLogoProps["size"]>, number> = {
  sm: 28,
  md: 36,
  lg: 52,
};

const TREND_PATH = "M6.5 28.5C11 27.5 12.5 13.5 17.2 13.8C21.5 14.1 22.2 26.2 27.2 22.8C30.4 20.6 33 12.8 35.2 10.2";

export function BrandLogo({ size = "sm", showWordmark = true }: BrandLogoProps) {
  const px = MARK_PX[size];
  return (
    <span className={`brand-logo brand-logo-${size}`}>
      <svg className="brand-mark" width={px} height={px} viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <rect width="40" height="40" rx="10" fill="#0a0e14" />
        <path d={TREND_PATH} stroke="#2ec4b6" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="35.2" cy="10.2" r="2.9" fill="#e8a87c" />
      </svg>
      {showWordmark && <span className="brand-wordmark">{BRAND_NAME}</span>}
    </span>
  );
}
