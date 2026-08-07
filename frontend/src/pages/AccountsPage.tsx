import { useEffect, useState, type FormEvent } from "react";
import { api, type Account, type AccountFlow } from "../api";
import { MoneyFlowGraph } from "../components/MoneyFlowGraph";
import { euro, parseEmployerNames } from "../format";

const ACCOUNT_TYPE_INVESTMENT = "investment";
const DEFAULT_SNP_ACCOUNT_NAME = "S&P 500";
const DEFAULT_SNP_INSTITUTION = "Index DCA";
const IMPORT_MODE_APPEND = "append";
const IMPORT_MODE_REPLACE = "replace";
const EMPLOYER_PLACEHOLDER = "PayPal, HP, …";
const FLOW_MONTH_LOOKBACK = 24;
const FLOW_MONTH_LOCALE = "en-US";

type MonthOption = { year: number; month: number; value: string; label: string };

function buildFlowMonthOptions(): MonthOption[] {
  const options: MonthOption[] = [];
  const cursor = new Date();
  cursor.setDate(1);
  for (let i = 0; i < FLOW_MONTH_LOOKBACK; i++) {
    const year = cursor.getFullYear();
    const month = cursor.getMonth() + 1;
    options.push({
      year,
      month,
      value: `${year}-${String(month).padStart(2, "0")}`,
      label: cursor.toLocaleDateString(FLOW_MONTH_LOCALE, { month: "short", year: "numeric" }),
    });
    cursor.setMonth(cursor.getMonth() - 1);
  }
  return options;
}

const FLOW_MONTH_OPTIONS = buildFlowMonthOptions();

function maskIban(iban: string | null): string {
  if (!iban) return "—";
  return iban.length <= 4 ? iban : `…${iban.slice(-4)}`;
}

export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [iban, setIban] = useState("");
  const [accountType, setAccountType] = useState("checking");
  const [employerNames, setEmployerNames] = useState("");
  const [balanceAccountId, setBalanceAccountId] = useState<number | "">("");
  const [balanceAmount, setBalanceAmount] = useState("");
  const [investAccountId, setInvestAccountId] = useState<number | "">("");
  const [investFile, setInvestFile] = useState<File | null>(null);
  const [investMode, setInvestMode] = useState<typeof IMPORT_MODE_APPEND | typeof IMPORT_MODE_REPLACE>(IMPORT_MODE_APPEND);
  const [message, setMessage] = useState("");
  const [flowMonth, setFlowMonth] = useState(FLOW_MONTH_OPTIONS[0]?.value ?? "");
  const [flow, setFlow] = useState<AccountFlow | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editIban, setEditIban] = useState("");

  const investmentAccounts = accounts.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
  const selectedInvestAccount = investmentAccounts.find((account) => account.id === investAccountId);
  const selectedFlowMonth = FLOW_MONTH_OPTIONS.find((option) => option.value === flowMonth) ?? FLOW_MONTH_OPTIONS[0];

  async function loadFlow(year: number, month: number) {
    setFlowLoading(true);
    const next = await api.accountFlow(year, month);
    setFlow(next);
    setFlowLoading(false);
  }

  async function loadAccounts() {
    const list = await api.accounts();
    setAccounts(list);
    if (!balanceAccountId && list[0]) setBalanceAccountId(list[0].id);
    const investList = list.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
    if (investList.length === 1) setInvestAccountId(investList[0].id);
    else if (investAccountId !== "" && !investList.some((account) => account.id === investAccountId)) setInvestAccountId("");
  }

  useEffect(() => {
    loadAccounts().catch((err: Error) => setMessage(err.message));
  }, []);

  useEffect(() => {
    if (!selectedFlowMonth) return;
    setFlowLoading(true);
    api.accountFlow(selectedFlowMonth.year, selectedFlowMonth.month)
      .then(setFlow)
      .catch((err: Error) => setMessage(err.message))
      .then(() => setFlowLoading(false));
  }, [flowMonth]);

  async function refreshAll() {
    await loadAccounts();
    if (selectedFlowMonth) await loadFlow(selectedFlowMonth.year, selectedFlowMonth.month);
  }

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    await api.createAccount({ name, institution, account_type: accountType, source: "manual", iban: iban || null });
    const companies = parseEmployerNames(employerNames);
    const employerNote = companies.length ? ` Employers saved: ${(await api.registerEmployers(companies)).companies.join(", ")}.` : "";
    setName("");
    setInstitution("");
    setIban("");
    setEmployerNames("");
    setMessage(`Account created.${employerNote}`);
    await refreshAll();
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
    await refreshAll();
  }

  async function saveBalance(event: FormEvent) {
    event.preventDefault();
    if (!balanceAccountId) return;
    await api.addBalance(Number(balanceAccountId), Number(balanceAmount));
    setBalanceAmount("");
    setMessage("Balance snapshot saved");
    await refreshAll();
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
    await refreshAll();
  }

  function startEdit(account: Account) {
    setEditingId(account.id);
    setEditName(account.name);
    setEditIban(account.iban ?? "");
  }

  async function saveEdit(accountId: number) {
    await api.updateAccount(accountId, { name: editName, iban: editIban.trim() ? editIban : null });
    setEditingId(null);
    setMessage("Account updated. Matching transfers reclassified.");
    await api.classifyTransactions();
    await refreshAll();
  }

  async function saveGraphIban(accountId: number, nextIban: string | null) {
    await api.updateAccount(accountId, { iban: nextIban });
    setMessage("IBAN saved. Matching transfers reclassified.");
    await api.classifyTransactions();
    await refreshAll();
  }

  async function quickAddAccount(input: { name: string; iban: string | null; account_type: string }) {
    await api.createAccount({ name: input.name, iban: input.iban, account_type: input.account_type, source: "manual" });
    setMessage(`Added “${input.name}”.`);
    await refreshAll();
  }

  async function removeAccount(accountId: number, label: string) {
    const confirmed = window.confirm(`Remove “${label}” from your accounts? It will leave the money-flow graph.`);
    if (!confirmed) return;
    await api.deleteAccount(accountId);
    if (editingId === accountId) setEditingId(null);
    if (balanceAccountId === accountId) setBalanceAccountId("");
    if (investAccountId === accountId) setInvestAccountId("");
    setMessage(`Removed “${label}”.`);
    await refreshAll();
  }

  return (
    <div>
      <section className="hero">
        <h1>Accounts</h1>
        <p>Add or remove accounts on the graph. Set IBANs so transfers between your own accounts stay out of expenses. Edge thickness is the link amount.</p>
      </section>

      <div className="panel flow-panel">
        <div className="flow-panel-head">
          <h2>Money flow</h2>
          <label className="flow-month">
            <span className="muted">Month</span>
            <select value={flowMonth} onChange={(e) => setFlowMonth(e.target.value)}>
              {FLOW_MONTH_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
        <MoneyFlowGraph
          flow={flow}
          loading={flowLoading}
          onSaveIban={(accountId, nextIban) => saveGraphIban(accountId, nextIban).catch((err: Error) => { setMessage(err.message); throw err; })}
          onAddAccount={(input) => quickAddAccount(input).catch((err: Error) => { setMessage(err.message); throw err; })}
          onRemoveAccount={(accountId, label) => removeAccount(accountId, label).catch((err: Error) => { setMessage(err.message); throw err; })}
        />
      </div>

      <div className="grid two">
        <div className="panel">
          <h2>Balances</h2>
          <table className="table">
            <thead><tr><th>Name</th><th>IBAN</th><th>Institution</th><th>Type</th><th>Balance</th><th /></tr></thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}>
                  {editingId === a.id ? (
                    <>
                      <td><input value={editName} onChange={(e) => setEditName(e.target.value)} /></td>
                      <td><input value={editIban} onChange={(e) => setEditIban(e.target.value)} placeholder="ES00…" /></td>
                      <td>{a.institution || "—"}</td>
                      <td>{a.account_type}</td>
                      <td>{euro.format(a.latest_balance ?? 0)}</td>
                      <td className="flow-edit-actions">
                        <button type="button" onClick={() => saveEdit(a.id).catch((err: Error) => setMessage(err.message))}>Save</button>
                        <button type="button" className="secondary" onClick={() => setEditingId(null)}>Cancel</button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{a.name}</td>
                      <td className="muted">{maskIban(a.iban)}</td>
                      <td>{a.institution || "—"}</td>
                      <td>{a.account_type}</td>
                      <td>{euro.format(a.latest_balance ?? 0)}</td>
                      <td className="flow-edit-actions">
                        <button type="button" className="secondary" onClick={() => startEdit(a)}>Edit</button>
                        <button type="button" className="secondary" onClick={() => removeAccount(a.id, a.name).catch((err: Error) => setMessage(err.message))}>Remove</button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Add manual account</h2>
          <form className="form" onSubmit={(e) => createAccount(e).catch((err: Error) => setMessage(err.message))}>
            <label><div className="muted">Name</div><input value={name} onChange={(e) => setName(e.target.value)} required /></label>
            <label><div className="muted">IBAN</div><input value={iban} onChange={(e) => setIban(e.target.value)} placeholder="ES91 2100 …" /></label>
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
