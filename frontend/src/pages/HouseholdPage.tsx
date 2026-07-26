import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

export function HouseholdPage() {
  const { user, household, refreshHousehold, refreshUser } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name || "");
  const [householdName, setHouseholdName] = useState(household?.name || "");
  const [location, setLocation] = useState(household?.location || "");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDisplayName(user?.display_name || "");
    setHouseholdName(household?.name || "");
    setLocation(household?.location || "");
  }, [user, household]);

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage("");
    await api.updateProfile({ display_name: displayName, household_name: householdName, location });
    await Promise.all([refreshHousehold(), refreshUser()]);
    setMessage("Profile saved. Category benchmarks will refresh on the dashboard.");
    setSaving(false);
  }

  return (
    <div>
      <section className="hero">
        <h1>Profile</h1>
        <p>Set your city or country so Spend by category can show typical monthly amounts for your location and salary.</p>
      </section>
      <div className="panel" style={{ maxWidth: 520 }}>
        <form className="stack-form" onSubmit={(e) => saveProfile(e).catch((err: Error) => { setMessage(err.message); setSaving(false); })}>
          <label>
            <div className="muted">Display name</div>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </label>
          <label>
            <div className="muted">Household name</div>
            <input value={householdName} onChange={(e) => setHouseholdName(e.target.value)} required />
          </label>
          <label>
            <div className="muted">Location (city, country)</div>
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Barcelona, Spain" />
          </label>
          <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
        </form>
        {message && <p className="muted" style={{ marginTop: "0.75rem" }}>{message}</p>}
        <div style={{ marginTop: "1.5rem" }}>
          <div className="stat-label">Invite code</div>
          <div className="stat-value" style={{ letterSpacing: "0.04em" }}>{household?.invite_code}</div>
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            Partner opens the app → Join → paste this code. Signed in as {user?.display_name} ({user?.role}).
          </p>
        </div>
      </div>
    </div>
  );
}
