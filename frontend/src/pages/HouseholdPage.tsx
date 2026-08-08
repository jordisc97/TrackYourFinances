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
    setMessage("Profile saved. Location benchmarks updated for Spend by category.");
    setSaving(false);
  }

  return (
    <div>
      <section className="hero">
        <h1>Profile</h1>
        <p>Set city or country so Spend by category can show typical amounts for your location and salary.</p>
      </section>
      <div className="panel profile-panel">
        <form className="stack-form" onSubmit={(e) => saveProfile(e).catch((err: Error) => { setMessage(err.message); setSaving(false); })}>
          <label>
            <div className="muted">Display name</div>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </label>
          <label>
            <div className="muted">Household name</div>
            <input value={householdName} onChange={(e) => setHouseholdName(e.target.value)} required />
          </label>
          <label data-tour="profile-location">
            <div className="muted">Location (city, country)</div>
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Barcelona, Spain" />
          </label>
          <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
        </form>
        {message && <p className="muted profile-message">{message}</p>}
        <div className="profile-invite">
          <div className="stat-label">Invite code</div>
          <div className="stat-value profile-invite-code">{household?.invite_code}</div>
          <p className="muted">
            Partner opens the app, chooses Join, then pastes this code. Signed in as {user?.display_name} ({user?.role}).
          </p>
        </div>
      </div>
    </div>
  );
}
