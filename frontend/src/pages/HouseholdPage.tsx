import { useAuth } from "../auth";

export function HouseholdPage() {
  const { user, household, refreshHousehold } = useAuth();
  return (
    <div>
      <section className="hero">
        <h1>Household</h1>
        <p>Share one ledger with your partner. They join with the invite code below.</p>
      </section>
      <div className="panel" style={{ maxWidth: 520 }}>
        <h2>{household?.name}</h2>
        <p className="muted">Signed in as {user?.display_name} ({user?.role})</p>
        <div style={{ marginTop: "1rem" }}>
          <div className="stat-label">Invite code</div>
          <div className="stat-value" style={{ letterSpacing: "0.04em" }}>{household?.invite_code}</div>
        </div>
        <p className="muted" style={{ marginTop: "1rem" }}>
          Partner opens the app → Join → paste this code, create their login, and they see the same accounts and dashboard.
        </p>
        <button type="button" className="secondary" onClick={() => refreshHousehold()}>Refresh</button>
      </div>
    </div>
  );
}
