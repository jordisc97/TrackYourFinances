import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Institution } from "../api";

export function OnboardingPage() {
  const navigate = useNavigate();
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("bank_status") === "failed") {
      setMessage(params.get("bank_message") || "Bank login failed. Try again or skip for now.");
      window.history.replaceState({}, "", "/onboarding");
    }
    if (params.get("bank_status") === "connected") {
      sessionStorage.removeItem("tyf_needs_onboarding");
      navigate("/?bank_status=connected&bank_message=" + encodeURIComponent(params.get("bank_message") || "Bank connected."), { replace: true });
      return;
    }
    api.institutions().then(setInstitutions).catch((err: Error) => setMessage(err.message));
  }, [navigate]);

  async function connect(id: string) {
    setBusyId(id);
    setMessage("");
    const result = await api.connect(id);
    window.location.href = result.authorization_url;
  }

  return (
    <div>
      <section className="hero">
        <div className="pill">Step 1 of 1</div>
        <h1>Connect your bank account</h1>
        <p>
          Link a bank so we can pull balances and transactions automatically.
          Right now Enable Banking is in <strong>Sandbox</strong> — use the test user below, not your real Sabadell password.
          Real Revolut/Sabadell needs a Production app later (or CSV import).
        </p>
        <div className="panel" style={{ marginTop: "1rem", background: "rgba(196,92,38,0.08)" }}>
          <strong>Sandbox login (Banco de Sabadell)</strong>
          <p className="muted" style={{ margin: "0.35rem 0 0" }}>
            User <code>user1</code> · Password <code>1234</code> · OTP / confirmation key <code>012345</code>
          </p>
        </div>
      </section>

      <div className="panel" style={{ maxWidth: 640 }}>
        <h2>Choose a bank</h2>
        {institutions.length === 0 && <p className="muted">Loading banks…</p>}
        <div style={{ display: "grid", gap: "0.75rem", marginTop: "1rem" }}>
          {institutions.map((inst) => (
            <div key={inst.id} className="row" style={{ alignItems: "center", borderBottom: "1px solid var(--line)", paddingBottom: "0.75rem" }}>
              <div style={{ flex: 2 }}>
                <strong>{inst.name}</strong>
                <div className="muted">{inst.country}</div>
              </div>
              <button type="button" disabled={busyId === inst.id} onClick={() => connect(inst.id).catch((e: Error) => { setBusyId(null); setMessage(e.message); })}>
                {busyId === inst.id ? "Redirecting…" : "Connect"}
              </button>
            </div>
          ))}
        </div>
        {message && <p className="amount-neg" style={{ marginTop: "1rem" }}>{message}</p>}
        <div className="row" style={{ marginTop: "1.5rem" }}>
          <button type="button" className="secondary" onClick={() => { sessionStorage.removeItem("tyf_needs_onboarding"); sessionStorage.setItem("tyf_onboarding_skipped", "1"); navigate("/"); }}>Skip for now</button>
          <Link to="/transactions" className="muted" style={{ alignSelf: "center" }}>Import CSV instead →</Link>
        </div>
      </div>
    </div>
  );
}
