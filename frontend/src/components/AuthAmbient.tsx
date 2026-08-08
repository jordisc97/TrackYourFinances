const AMBIENT_ORBS = ["a", "b", "c", "d", "e", "f"] as const;

const AMBIENT_CHIPS = [
  { id: "chip-up", label: "+12.4%", detail: "This month", tone: "up" },
  { id: "chip-bal", label: "€2,480", detail: "Cash buffer", tone: "neutral" },
  { id: "chip-save", label: "Save 18%", detail: "Of income", tone: "up" },
  { id: "chip-fx", label: "EUR → USD", detail: "Open banking", tone: "warm" },
  { id: "chip-goal", label: "Goal 74%", detail: "Wealth track", tone: "up" },
] as const;

const TREND_PATH = "M8 88C48 84 62 40 98 46C128 51 142 78 178 58C208 42 232 22 272 18";

export function AuthAmbient() {
  return (
    <div className="auth-ambient" aria-hidden="true">
      <div className="auth-ambient-wash" />
      <div className="auth-ambient-grid" />
      {AMBIENT_ORBS.map((orb) => (
        <span key={orb} className={`auth-orb auth-orb-${orb}`} />
      ))}
      <span className="auth-ring auth-ring-a" />
      <span className="auth-ring auth-ring-b" />
      <span className="auth-ring auth-ring-c" />
      <svg className="auth-trendline auth-trendline-a" viewBox="0 0 280 120" fill="none">
        <path d={TREND_PATH} stroke="url(#auth-trend-a)" strokeWidth="2.4" strokeLinecap="round" />
        <circle cx="272" cy="18" r="4.5" fill="#e8a87c" />
        <defs>
          <linearGradient id="auth-trend-a" x1="8" y1="88" x2="272" y2="18" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2ec4b6" stopOpacity=".2" />
            <stop offset="1" stopColor="#2ec4b6" stopOpacity="1" />
          </linearGradient>
        </defs>
      </svg>
      <svg className="auth-trendline auth-trendline-b" viewBox="0 0 280 120" fill="none">
        <path d={TREND_PATH} stroke="url(#auth-trend-b)" strokeWidth="2" strokeLinecap="round" strokeOpacity=".45" />
        <circle cx="272" cy="18" r="3.5" fill="#e8a87c" fillOpacity=".7" />
        <defs>
          <linearGradient id="auth-trend-b" x1="8" y1="88" x2="272" y2="18" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2ec4b6" stopOpacity=".1" />
            <stop offset="1" stopColor="#67e8f9" stopOpacity=".8" />
          </linearGradient>
        </defs>
      </svg>
      {AMBIENT_CHIPS.map((chip) => (
        <div key={chip.id} className={`auth-float-chip auth-float-${chip.id} auth-float-${chip.tone}`}>
          <strong>{chip.label}</strong>
          <span>{chip.detail}</span>
        </div>
      ))}
    </div>
  );
}
