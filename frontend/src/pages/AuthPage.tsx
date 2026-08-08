import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";

type Mode = "login" | "register" | "join";

const MODE_LABELS: Record<Mode, string> = {
  login: "Sign in",
  register: "Create household",
  join: "Join with invite",
};

const MIN_PASSWORD_LENGTH = 8;

export function AuthPage() {
  const { login, register, join } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [householdName, setHouseholdName] = useState("Our household");
  const [inviteCode, setInviteCode] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode !== "login" && password !== passwordConfirm) {
      setError("Passwords do not match");
      return;
    }
    if (mode === "register") {
      await register({ email, password, display_name: displayName, household_name: householdName }).catch((err: Error) => setError(err.message));
      return;
    }
    if (mode === "join") {
      await join({ email, password, display_name: displayName, invite_code: inviteCode.trim() }).catch((err: Error) => setError(err.message));
      return;
    }
    await login(email, password).catch((err: Error) => setError(err.message));
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>TrackYourFinances</h1>
        <p className="muted">Household money, Revolut & Sabadell first — private by default.</p>
        <div className="tabs">
          {(Object.keys(MODE_LABELS) as Mode[]).map((item) => (
            <button key={item} type="button" className={mode === item ? "active" : ""} onClick={() => setMode(item)}>
              {MODE_LABELS[item]}
            </button>
          ))}
        </div>
        <form className="form" onSubmit={onSubmit}>
          {mode !== "login" && (
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
          {mode === "join" && (
            <label>
              <div className="muted">Invite code</div>
              <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} required autoComplete="off" />
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
          {mode !== "login" && (
            <label>
              <div className="muted">Confirm password</div>
              <input type="password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} autoComplete="new-password" />
            </label>
          )}
          {mode !== "login" && <p className="muted">Use at least {MIN_PASSWORD_LENGTH} characters with a letter and a digit.</p>}
          {error && <p className="amount-neg">{error}</p>}
          <button type="submit">{MODE_LABELS[mode]}</button>
        </form>
      </div>
    </div>
  );
}
