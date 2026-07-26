import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type BankConnection, type Institution } from "../api";

export function BanksPage() {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [connections, setConnections] = useState<BankConnection[]>([]);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "err">("ok");
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    const [inst, conn] = await Promise.all([api.institutions(), api.connections()]);
    setInstitutions(inst);
    setConnections(conn);
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("bank_status");
    const bankMessage = params.get("bank_message");
    if (status && bankMessage) {
      setMessage(bankMessage);
      setMessageTone(status === "failed" ? "err" : "ok");
      window.history.replaceState({}, "", "/banks");
    }
    load().catch((err: Error) => { setMessage(err.message); setMessageTone("err"); });
  }, []);

  async function connect(id: string) {
    setBusyId(id);
    setMessage("");
    const result = await api.connect(id);
    window.location.href = result.authorization_url;
  }

  async function sync(id: number) {
    const result = await api.sync(id);
    setMessage(`Synced — imported ${result.imported}`);
    setMessageTone("ok");
    await load();
  }

  async function reconnect(id: number) {
    const result = await api.reconnect(id);
    window.location.href = result.authorization_url;
  }

  return (
    <div>
      <section className="hero">
        <h1>Banks</h1>
        <p>
          Connect via Enable Banking (<strong>Sandbox</strong>). Do not use your real Sabadell password here.
          Test user: <code>user1</code> / <code>1234</code> / OTP <code>012345</code>.
          Revolut is not in sandbox — use Production later or CSV import.
        </p>
        {connections.length === 0 && (
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            No bank linked yet — connect below, or <Link to="/transactions">import a CSV</Link>.
          </p>
        )}
      </section>

      <div className="grid two">
        <div className="panel">
          <h2>Available institutions</h2>
          <table className="table">
            <thead><tr><th>Bank</th><th>Country</th><th></th></tr></thead>
            <tbody>
              {institutions.map((inst) => (
                <tr key={inst.id}>
                  <td>{inst.name}</td>
                  <td>{inst.country}</td>
                  <td>
                    <button type="button" disabled={busyId === inst.id} onClick={() => connect(inst.id).catch((e: Error) => { setBusyId(null); setMessage(e.message); setMessageTone("err"); })}>
                      {busyId === inst.id ? "Redirecting…" : "Connect"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Connections</h2>
          <table className="table">
            <thead><tr><th>Institution</th><th>Status</th><th>Consent</th><th></th></tr></thead>
            <tbody>
              {connections.map((c) => (
                <tr key={c.id}>
                  <td>{c.institution_name}</td>
                  <td><span className={c.status === "expired" ? "pill warn" : "pill"}>{c.status}</span></td>
                  <td>{c.consent_expires_at ? new Date(c.consent_expires_at).toLocaleDateString() : "—"}</td>
                  <td className="row">
                    <button type="button" className="secondary" onClick={() => sync(c.id).catch((e: Error) => { setMessage(e.message); setMessageTone("err"); })}>Sync</button>
                    <button type="button" onClick={() => reconnect(c.id).catch((e: Error) => { setMessage(e.message); setMessageTone("err"); })}>Reconnect</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {message && <p className={messageTone === "err" ? "amount-neg" : "muted"}>{message}</p>}
        </div>
      </div>
    </div>
  );
}
