import { useEffect, useState, type FormEvent } from "react";
import { api, type Account } from "../api";
import { euro, parseEmployerNames } from "../format";

const ACCOUNT_TYPE_INVESTMENT = "investment";
const DEFAULT_SNP_ACCOUNT_NAME = "S&P 500";
const DEFAULT_SNP_INSTITUTION = "Index DCA";
const IMPORT_MODE_APPEND = "append";
const IMPORT_MODE_REPLACE = "replace";
const EMPLOYER_PLACEHOLDER = "PayPal, HP, …";

export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [accountType, setAccountType] = useState("checking");
  const [employerNames, setEmployerNames] = useState("");
  const [balanceAccountId, setBalanceAccountId] = useState<number | "">("");
  const [balanceAmount, setBalanceAmount] = useState("");
  const [investAccountId, setInvestAccountId] = useState<number | "">("");
  const [investFile, setInvestFile] = useState<File | null>(null);
  const [investMode, setInvestMode] = useState<typeof IMPORT_MODE_APPEND | typeof IMPORT_MODE_REPLACE>(IMPORT_MODE_APPEND);
  const [message, setMessage] = useState("");

  const investmentAccounts = accounts.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
  const selectedInvestAccount = investmentAccounts.find((account) => account.id === investAccountId);

  async function load() {
    const list = await api.accounts();
    setAccounts(list);
    if (!balanceAccountId && list[0]) setBalanceAccountId(list[0].id);
    const investList = list.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
    if (investList.length === 1) setInvestAccountId(investList[0].id);
    else if (investAccountId !== "" && !investList.some((account) => account.id === investAccountId)) setInvestAccountId("");
  }

  useEffect(() => {
    load().catch((err: Error) => setMessage(err.message));
  }, []);

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    await api.createAccount({ name, institution, account_type: accountType, source: "manual" });
    const companies = parseEmployerNames(employerNames);
    const employerNote = companies.length ? ` Employers saved: ${(await api.registerEmployers(companies)).companies.join(", ")}.` : "";
    setName("");
    setInstitution("");
    setEmployerNames("");
    setMessage(`Account created.${employerNote}`);
    await load();
  }

  async function createSnpAccount() {
    const created = await api.createAccount({
      name: DEFAULT_SNP_ACCOUNT_NAME,
      institution: DEFAULT_SNP_INSTITUTION,
      account_type: ACCOUNT_TYPE_INVESTMENT,
      source: "manual",
    });
    setInvestAccountId(created.id);
    setMessage(`Created “${created.name}”. Import investment history below.`);
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

  async function importInvestmentHistory(event: FormEvent) {
    event.preventDefault();
    if (!investFile || investAccountId === "") {
      setMessage("Select an investment account and CSV file first.");
      return;
    }
    const overwrite = investMode === IMPORT_MODE_REPLACE;
    if (overwrite) {
      const confirmed = window.confirm(`Replace every balance snapshot on “${selectedInvestAccount?.name ?? "this account"}” with this CSV?`);
      if (!confirmed) return;
    }
    const result = await api.importInvestmentCsv(Number(investAccountId), investFile, overwrite);
    const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`];
    if (result.overwrite) parts.splice(1, 0, `replaced ${result.replaced}`);
    setMessage(`${parts.join(" · ")} → ${selectedInvestAccount?.name ?? "account"}`);
    setInvestFile(null);
    setInvestMode(IMPORT_MODE_APPEND);
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
            <label>
              <div className="muted">Employers / salary companies</div>
              <input value={employerNames} onChange={(e) => setEmployerNames(e.target.value)} placeholder={EMPLOYER_PLACEHOLDER} />
              <span className="muted" style={{ fontSize: "0.85rem" }}>Comma-separated. Matching inflows count as wage Income; other positives as Transfers.</span>
            </label>
            <button type="submit">Create</button>
          </form>
          <button type="button" className="secondary" style={{ marginTop: "0.75rem" }} onClick={() => createSnpAccount().catch((err: Error) => setMessage(err.message))}>
            Add S&amp;P 500 investment
          </button>
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
          <h3 style={{ marginTop: "1.5rem" }}>Import investment history</h3>
          <p className="muted">CSV with <code>date</code> and <code>account_value_eur</code>. Keeps market value via balance snapshots.</p>
          <form className="form" onSubmit={(e) => importInvestmentHistory(e).catch((err: Error) => setMessage(err.message))}>
            <label>
              <div className="muted">Investment account</div>
              <select value={investAccountId} onChange={(e) => setInvestAccountId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Select…</option>
                {investmentAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label>
              <div className="muted">CSV file</div>
              <input type="file" accept=".csv,text/csv" onChange={(e) => setInvestFile(e.target.files?.[0] ?? null)} />
            </label>
            <label>
              <div className="muted">Mode</div>
              <select value={investMode} onChange={(e) => setInvestMode(e.target.value as typeof IMPORT_MODE_APPEND | typeof IMPORT_MODE_REPLACE)}>
                <option value={IMPORT_MODE_APPEND}>Append / upsert</option>
                <option value={IMPORT_MODE_REPLACE}>Replace snapshots</option>
              </select>
            </label>
            <button type="submit" disabled={!investFile || investAccountId === ""}>Import history</button>
          </form>
          {message && <p className="muted">{message}</p>}
        </div>
      </div>
    </div>
  );
}
