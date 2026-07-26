import { useEffect, useState, type FormEvent } from "react";
import { api, type Account } from "../api";

const euro = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });

export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [accountType, setAccountType] = useState("checking");
  const [balanceAccountId, setBalanceAccountId] = useState<number | "">("");
  const [balanceAmount, setBalanceAmount] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const list = await api.accounts();
    setAccounts(list);
    if (!balanceAccountId && list[0]) setBalanceAccountId(list[0].id);
  }

  useEffect(() => {
    load().catch((err: Error) => setMessage(err.message));
  }, []);

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    await api.createAccount({ name, institution, account_type: accountType, source: "manual" });
    setName("");
    setInstitution("");
    setMessage("Account created");
    await load();
  }

  async function saveBalance(event: FormEvent) {
    event.preventDefault();
    if (!balanceAccountId) return;
    await api.addBalance(Number(balanceAccountId), Number(balanceAmount));
    setBalanceAmount("");
    setMessage("Balance snapshot saved");
    await load();
  }

  return (
    <div>
      <section className="hero">
        <h1>Accounts</h1>
        <p>Manual balances for brokers and anything Open Banking does not cover yet.</p>
      </section>

      <div className="grid two">
        <div className="panel">
          <h2>Balances</h2>
          <table className="table">
            <thead><tr><th>Name</th><th>Institution</th><th>Type</th><th>Balance</th></tr></thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{a.institution || "—"}</td>
                  <td>{a.account_type}</td>
                  <td>{euro.format(a.latest_balance ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Add manual account</h2>
          <form className="form" onSubmit={(e) => createAccount(e).catch((err: Error) => setMessage(err.message))}>
            <label><div className="muted">Name</div><input value={name} onChange={(e) => setName(e.target.value)} required /></label>
            <label><div className="muted">Institution</div><input value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="Trade Republic, Coinbase…" /></label>
            <label>
              <div className="muted">Type</div>
              <select value={accountType} onChange={(e) => setAccountType(e.target.value)}>
                <option value="checking">checking</option>
                <option value="savings">savings</option>
                <option value="investment">investment</option>
                <option value="other">other</option>
              </select>
            </label>
            <button type="submit">Create</button>
          </form>
          <h3 style={{ marginTop: "1.5rem" }}>Record balance</h3>
          <form className="form" onSubmit={(e) => saveBalance(e).catch((err: Error) => setMessage(err.message))}>
            <label>
              <div className="muted">Account</div>
              <select value={balanceAccountId} onChange={(e) => setBalanceAccountId(Number(e.target.value))}>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label><div className="muted">Amount (EUR)</div><input type="number" step="0.01" value={balanceAmount} onChange={(e) => setBalanceAmount(e.target.value)} required /></label>
            <button type="submit">Save snapshot</button>
          </form>
          {message && <p className="muted">{message}</p>}
        </div>
      </div>
    </div>
  );
}
