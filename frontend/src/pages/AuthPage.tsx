import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";

type Mode = "login" | "register" | "join";

export function AuthPage() {
  const { login, register, join } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [householdName, setHouseholdName] = useState("Our household");
  const [inviteCode, setInviteCode] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "register") {
      await register({ email, password, display_name: displayName, household_name: householdName }).catch((err: Error) => setError(err.message));
      return;
    }
    if (mode === "join") {
      await join({ email, password, display_name: displayName, invite_code: inviteCode }).catch((err: Error) => setError(err.message));
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
          {(["login", "register", "join"] as Mode[]).map((item) => (
            <button key={item} type="button" className={mode === item ? "active" : ""} onClick={() => setMode(item)}>
              {item}
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
              <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} required />
            </label>
          )}
          <label>
            <div className="muted">Email</div>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            <div className="muted">Password</div>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </label>
          {error && <p className="amount-neg">{error}</p>}
          <button type="submit">{mode === "login" ? "Sign in" : mode === "register" ? "Create household" : "Join household"}</button>
        </form>
      </div>
    </div>
  );
}
