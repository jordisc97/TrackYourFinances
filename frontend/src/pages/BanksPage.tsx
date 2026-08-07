import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type BankConnection, type Institution } from "../api";

type PsuType = "personal" | "business";

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

function formatWhen(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function statusClass(status: string) {
  if (status === "active") return "pill";
  if (status === "expired" || status === "error") return "pill warn";
  return "pill";
}

export function BanksPage() {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [connections, setConnections] = useState<BankConnection[]>([]);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "err">("ok");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [psuType, setPsuType] = useState<PsuType>("personal");

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

  const linked = useMemo(() => {
    const byBank = new Map<string, BankConnection>();
    for (const connection of connections) {
      if (connection.status !== "active" || connection.is_mock) continue;
      const key = connection.institution_name;
      const current = byBank.get(key);
      if (!current || new Date(connection.created_at) > new Date(current.created_at)) byBank.set(key, connection);
    }
    return [...byBank.values()].sort((a, b) => a.institution_name.localeCompare(b.institution_name));
  }, [connections]);

  const recent = useMemo(() => [...connections].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 5), [connections]);

  async function connect(id: string) {
    setBusyId(id);
    setMessage("");
    try {
      const result = await api.connect(id, psuType);
      window.location.href = result.authorization_url;
    } catch (err) {
      setBusyId(null);
      setMessageTone("err");
      setMessage(err instanceof Error ? err.message : "Connect failed");
    }
  }

  async function sync(id: number) {
    const result = await api.sync(id);
    setMessage(`Synced — imported ${result.imported}`);
    setMessageTone("ok");
    await load();
  }

  async function reconnect(id: number) {
    const result = await api.reconnect(id, psuType);
    window.location.href = result.authorization_url;
  }

  return (
    <div>
      <section className="hero">
        <h1>Banks</h1>
        <p>
          Open Banking links for live balances and transactions. CSV imports live under{" "}
          <Link to="/accounts">Accounts</Link> / <Link to="/transactions">Transactions</Link>, not here.
        </p>
        {message && <p className={messageTone === "err" ? "amount-neg" : "muted"} style={{ marginTop: "0.75rem" }}>{message}</p>}
      </section>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2>Connected now</h2>
        {linked.length === 0 ? (
          <p className="muted">No active bank link yet.</p>
        ) : (
          <table className="table">
            <thead><tr><th>Bank</th><th>Consent until</th><th>Last synced</th><th></th></tr></thead>
            <tbody>
              {linked.map((c) => (
                <tr key={c.id}>
                  <td>{c.institution_name}</td>
                  <td>{formatDate(c.consent_expires_at)}</td>
                  <td>{formatWhen(c.last_synced_at)}</td>
                  <td className="row">
                    <button type="button" className="secondary" onClick={() => sync(c.id).catch((e: Error) => { setMessage(e.message); setMessageTone("err"); })}>Sync</button>
                    <button type="button" onClick={() => reconnect(c.id).catch((e: Error) => { setMessage(e.message); setMessageTone("err"); })}>Reconnect</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid two">
        <div className="panel">
          <h2>Connect a bank</h2>
          <label className="bank-psu">
            <div className="muted">Account type at the bank</div>
            <select value={psuType} onChange={(e) => setPsuType(e.target.value as PsuType)}>
              <option value="personal">Personal</option>
              <option value="business">Business</option>
            </select>
          </label>
          {institutions.length === 0 ? (
            <p className="muted">No banks available from the provider right now.</p>
          ) : (
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
          )}
        </div>

        <div className="panel">
          <h2>Last 5 connection attempts</h2>
          <table className="table">
            <thead><tr><th>Bank</th><th>Tried</th><th>Status</th><th>Consent</th></tr></thead>
            <tbody>
              {recent.map((c) => (
                <tr key={c.id}>
                  <td>{c.institution_name}</td>
                  <td>{formatWhen(c.created_at)}</td>
                  <td><span className={statusClass(c.status)}>{c.status}</span></td>
                  <td>{formatDate(c.consent_expires_at)}</td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr><td colSpan={4} className="muted">No attempts yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
