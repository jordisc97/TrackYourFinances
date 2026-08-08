import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { AuthAmbient } from "../components/AuthAmbient";
import { BrandLogo } from "../components/BrandLogo";
import { useAuth } from "../auth";

type Mode = "login" | "register";

const MODE_LABELS: Record<Mode, string> = {
  login: "Log in",
  register: "Register",
};

const MODE_HINTS: Record<Mode, string> = {
  login: "Welcome back. Pick up where the household left off.",
  register: "Start a private space for shared balances and cashflow.",
};

const MIN_PASSWORD_LENGTH = 8;
const BRAND_HEADLINE = "Your wealth, simplified.";
const BRAND_SUPPORT = "Balances, cashflow, and open banking for European banks. Private by default.";

export function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [householdName, setHouseholdName] = useState("Our household");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "register" && password !== passwordConfirm) {
      setError("Passwords do not match");
      return;
    }
    if (mode === "register") {
      await register({ email, password, display_name: displayName, household_name: householdName }).catch((err: Error) => setError(err.message));
      return;
    }
    await login(email, password).catch((err: Error) => setError(err.message));
  }

  return (
    <div className="auth-shell">
      <AuthAmbient />
      <aside className="auth-brand" aria-label="Brand">
        <div className="auth-brand-copy">
          <BrandLogo size="lg" />
          <h1 className="auth-brand-headline">{BRAND_HEADLINE}</h1>
          <p className="auth-brand-support">{BRAND_SUPPORT}</p>
        </div>
      </aside>

      <main className="auth-gate">
        <div className="auth-gate-inner">
          <h2 className="auth-gate-title">{MODE_LABELS[mode]}</h2>
          <p className="muted auth-gate-hint">{MODE_HINTS[mode]}</p>
          <div className="tabs auth-tabs" role="tablist" aria-label="Account mode">
            {(Object.keys(MODE_LABELS) as Mode[]).map((item) => (
              <button key={item} type="button" role="tab" aria-selected={mode === item} className={mode === item ? "active" : ""} onClick={() => setMode(item)}>
                {MODE_LABELS[item]}
              </button>
            ))}
          </div>
          <form className="form auth-form" onSubmit={onSubmit}>
            {mode === "register" && (
              <label>
                <div className="muted">Display name</div>
                <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
              </label>
            )}
            {mode === "register" && (
              <label>
                <div className="muted">Household name</div>
                <input value={householdName} onChange={(e) => setHouseholdName(e.target.value)} required />
              </label>
            )}
            <label>
              <div className="muted">Email</div>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </label>
            <label>
              <div className="muted">Password</div>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </label>
            {mode === "register" && (
              <label>
                <div className="muted">Confirm password</div>
                <input type="password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} autoComplete="new-password" />
              </label>
            )}
            {mode === "register" && <p className="muted auth-password-hint">Use at least {MIN_PASSWORD_LENGTH} characters with a letter and a digit.</p>}
            {error && <p className="amount-neg" role="alert">{error}</p>}
            <button type="submit" className="auth-submit">{MODE_LABELS[mode]}</button>
          </form>
          <p className="auth-legal muted">
            <Link to="/privacy">Privacy</Link>
            <span aria-hidden="true"> · </span>
            <Link to="/terms">Terms</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
