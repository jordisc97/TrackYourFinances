import { useEffect, useState, type FormEvent } from "react";
import { api, type Account, type Category, type Transaction } from "../api";
import { euro } from "../format";

const ACCOUNT_UNSET = "" as const;
const TIMER_TICK_MS = 250;
const IMPORT_MODE_APPEND = "append";
const IMPORT_MODE_REPLACE = "replace";
const DEFAULT_CSV_ACCOUNT_NAME = "CSV checking";
const DEFAULT_CSV_INSTITUTION = "CSV import";

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [onlyUncategorized, setOnlyUncategorized] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "error" | "">("");
  const [accountId, setAccountId] = useState<number | typeof ACCOUNT_UNSET>(ACCOUNT_UNSET);
  const [file, setFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<typeof IMPORT_MODE_APPEND | typeof IMPORT_MODE_REPLACE>(IMPORT_MODE_APPEND);
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [newAccountName, setNewAccountName] = useState(DEFAULT_CSV_ACCOUNT_NAME);
  const [creatingAccount, setCreatingAccount] = useState(false);

  const selectedAccount = accounts.find((account) => account.id === accountId);
  const overwrite = importMode === IMPORT_MODE_REPLACE;
  const canImport = Boolean(file && accountId !== ACCOUNT_UNSET && !busy);

  async function load() {
    const [txs, cats, accs] = await Promise.all([api.transactions({ uncategorized: onlyUncategorized }), api.categories(), api.accounts()]);
    setTransactions(txs);
    setCategories(cats);
    setAccounts(accs);
    if (accs.length === 1) setAccountId(accs[0].id);
    else if (accountId !== ACCOUNT_UNSET && !accs.some((account) => account.id === accountId)) setAccountId(ACCOUNT_UNSET);
  }

  async function createImportAccount(event: FormEvent) {
    event.preventDefault();
    const name = newAccountName.trim() || DEFAULT_CSV_ACCOUNT_NAME;
    setCreatingAccount(true);
    const created = await api.createAccount({ name, institution: DEFAULT_CSV_INSTITUTION, account_type: "checking", source: "csv", currency: "EUR" });
    setAccounts((current) => [...current, created]);
    setAccountId(created.id);
    setMessageTone("ok");
    setMessage(`Created account “${created.name}”. You can import a CSV into it now.`);
    setCreatingAccount(false);
  }

  useEffect(() => {
    load().catch((err: Error) => { setMessageTone("error"); setMessage(err.message); });
  }, [onlyUncategorized]);

  useEffect(() => {
    if (!busy) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timerId = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), TIMER_TICK_MS);
    return () => window.clearInterval(timerId);
  }, [busy]);

  async function assign(txId: number, categoryId: number) {
    await api.assignCategory(txId, { category_id: categoryId, create_rule: true });
    await load();
  }

  async function onImport(event: FormEvent) {
    event.preventDefault();
    if (!file || accountId === ACCOUNT_UNSET) {
      setMessageTone("error");
      setMessage("Select an account and a CSV file before importing.");
      return;
    }
    if (overwrite) {
      const confirmed = window.confirm(`Replace every transaction on “${selectedAccount?.name ?? "this account"}” with this CSV? Existing rows on that account will be deleted.`);
      if (!confirmed) return;
    }
    setBusy(true);
    setMessage("");
    setMessageTone("");
    const result = await api.importCsv(Number(accountId), file, overwrite);
    const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`, `categorized ${result.categorized}`];
    if (result.overwrite) parts.splice(1, 0, `replaced ${result.replaced}`);
    setMessageTone("ok");
    setMessage(`${parts.join(" · ")} → ${selectedAccount?.name ?? "account"}`);
    setFile(null);
    setImportMode(IMPORT_MODE_APPEND);
    await load();
    setBusy(false);
  }

  return (
    <div>
      <section className="hero">
        <h1>Transactions</h1>
        <p>Classify spending, import bank CSVs, and grow rules from one-click assigns.</p>
      </section>

      <div className={`panel csv-import${busy ? " is-busy" : ""}`} style={{ marginBottom: "1rem" }}>
        <div className="csv-import-head">
          <div>
            <h2>Import bank CSV</h2>
            <p className="muted">Bank column names are mapped automatically. After upload, every transaction on that account is re-categorized.</p>
          </div>
        </div>

        <form className="csv-import-form" onSubmit={(e) => onImport(e).catch((err: Error) => { setBusy(false); setMessageTone("error"); setMessage(err.message); })}>
          <div className="csv-step">
            <span className="csv-step-num" aria-hidden="true">1</span>
            <div className="csv-step-body">
              <span className="csv-label">Account</span>
              <span className="csv-hint">Which account should receive these transactions?</span>
              {accounts.length === 0 ? (
                <form className="csv-create-account" onSubmit={(e) => createImportAccount(e).catch((err: Error) => { setCreatingAccount(false); setMessageTone("error"); setMessage(err.message); })}>
                  <p className="csv-empty">No accounts yet. Create one to import into — or add accounts under Accounts / Banks first.</p>
                  <div className="csv-create-row">
                    <input value={newAccountName} onChange={(e) => setNewAccountName(e.target.value)} placeholder="Account name" disabled={busy || creatingAccount} required />
                    <button type="submit" className="secondary" disabled={busy || creatingAccount}>{creatingAccount ? "Creating…" : "Create account"}</button>
                  </div>
                </form>
              ) : (
                <select value={accountId === ACCOUNT_UNSET ? "" : accountId} onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : ACCOUNT_UNSET)} required disabled={busy}>
                  <option value="" disabled>Select an account…</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.institution ? ` · ${a.institution}` : ""}</option>)}
                </select>
              )}
            </div>
          </div>

          <label className="csv-step">
            <span className="csv-step-num" aria-hidden="true">2</span>
            <span className="csv-step-body">
              <span className="csv-label">CSV file</span>
              <span className="csv-hint">Export from your bank, then choose the file here.</span>
              <span className={`csv-file${file ? " has-file" : ""}`}>
                <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required disabled={busy} />
                <span className="csv-file-name">{file ? file.name : "No file chosen"}</span>
                <span className="csv-file-action">{file ? "Change file" : "Choose CSV"}</span>
              </span>
            </span>
          </label>

          <fieldset className="csv-step csv-mode" disabled={busy}>
            <span className="csv-step-num" aria-hidden="true">3</span>
            <span className="csv-step-body">
              <legend className="csv-label">Import mode</legend>
              <span className="csv-hint">Choose whether to keep existing rows or start fresh on this account.</span>
              <div className="csv-mode-options">
                <label className={`csv-mode-option${importMode === IMPORT_MODE_APPEND ? " is-selected" : ""}`}>
                  <input type="radio" name="import-mode" checked={importMode === IMPORT_MODE_APPEND} onChange={() => setImportMode(IMPORT_MODE_APPEND)} />
                  <span>
                    <strong>Add new only</strong>
                    <span className="muted">Keep current transactions. Skip rows that already exist.</span>
                  </span>
                </label>
                <label className={`csv-mode-option${importMode === IMPORT_MODE_REPLACE ? " is-selected" : ""}`}>
                  <input type="radio" name="import-mode" checked={importMode === IMPORT_MODE_REPLACE} onChange={() => setImportMode(IMPORT_MODE_REPLACE)} />
                  <span>
                    <strong>Replace all on account</strong>
                    <span className="muted">Delete every transaction on this account, then import the CSV.</span>
                  </span>
                </label>
              </div>
            </span>
          </fieldset>

          <div className="csv-actions">
            <button type="submit" disabled={!canImport}>{busy ? "Working…" : "Import and categorize"}</button>
            {selectedAccount && file && !busy && (
              <p className="csv-summary muted">
                {overwrite ? "Replace" : "Add to"} <strong>{selectedAccount.name}</strong> from <strong>{file.name}</strong>
              </p>
            )}
          </div>
        </form>

        {message && <p className={`csv-status csv-status-${messageTone || "ok"}`}>{message}</p>}
      </div>

      <div className={`panel ledger-panel${busy ? " is-busy" : ""}`}>
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <h2 style={{ flex: 2 }}>Ledger</h2>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input type="checkbox" checked={onlyUncategorized} onChange={(e) => setOnlyUncategorized(e.target.checked)} disabled={busy} />
            Uncategorized inbox
          </label>
        </div>
        <div className={`ledger-body${busy ? " is-obscured" : ""}`}>
          <table className="table">
            <thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th>Assign</th></tr></thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{tx.booked_at}</td>
                  <td>{tx.merchant || tx.raw_description || "—"}</td>
                  <td className={tx.amount >= 0 ? "amount-pos" : "amount-neg"}>{euro.format(tx.amount)}</td>
                  <td>{tx.category_name || <span className="pill warn">Uncategorized</span>}</td>
                  <td>
                    <select defaultValue="" disabled={busy} onChange={(e) => { const value = Number(e.target.value); if (value) assign(tx.id, value).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); }); }}>
                      <option value="" disabled>Choose…</option>
                      {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {busy && (
          <div className="categorize-overlay" role="status" aria-live="polite">
            <div className="categorize-card">
              <div className="categorize-ring" aria-hidden="true">
                <span className="categorize-ring-spin" />
                <span className="categorize-ring-time">{formatElapsed(elapsedSeconds)}</span>
              </div>
              <h3>Categorizing your expenses</h3>
              <p className="muted">Reviewing merchants and assigning categories. The ledger will refresh when this finishes.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
