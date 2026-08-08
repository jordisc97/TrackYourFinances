import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type Account } from "../api";
import { useAuth } from "../auth";
import { markOnboardingComplete } from "../components/ProductTour";
import { euro, parseEmployerNames } from "../format";

const ACCOUNT_TYPE_INVESTMENT = "investment";
const DEFAULT_SNP_ACCOUNT_NAME = "S&P 500";
const DEFAULT_SNP_INSTITUTION = "Index DCA";
const IMPORT_MODE_APPEND = "append";
const IMPORT_MODE_REPLACE = "replace";
const EMPLOYER_PLACEHOLDER = "PayPal, HP, …";
const ACCOUNT_UNSET = "" as const;
const IMPORT_PHASE_IDLE = "idle";
const IMPORT_PHASE_IMPORTING = "importing";
const IMPORT_PHASE_CATEGORIZING = "categorizing";
const TIMER_TICK_MS = 250;
const ACCOUNT_MODE_EXISTING = "existing";
const ACCOUNT_MODE_CREATE = "create";
const DEFAULT_CSV_ACCOUNT_NAME = "CSV checking";
const DEFAULT_CSV_INSTITUTION = "CSV import";
const ACCOUNT_NAME_PLACEHOLDER = "e.g. Everyday checking";
const SETUP_QUERY_KEY = "setup";
const SETUP_QUERY_VALUE = "1";
const ACCOUNTS_PATH = "/accounts";
const USE_EXISTING_LABEL = "Use existing";
const CREATE_NEW_LABEL = "Create new";
const CREATE_ACCOUNT_HINT = "Name the new account. Import will create it, then load your file.";
const EMPTY_ACCOUNTS_HINT = "No accounts yet. Type a name below, choose your file, then Import and categorize.";
const NEED_ACCOUNT_OR_NAME_MESSAGE = "Name a new account or select an existing one, and choose a CSV/Excel file before importing.";
const CREATE_ACCOUNT_LABEL = "Create account";
const CREATING_ACCOUNT_LABEL = "Creating…";

function maskIban(iban: string | null): string {
  if (!iban) return "—";
  return iban.length <= 4 ? iban : `…${iban.slice(-4)}`;
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function AccountsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setupMode = searchParams.get(SETUP_QUERY_KEY) === SETUP_QUERY_VALUE;
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
  const [messageTone, setMessageTone] = useState<"ok" | "error" | "">("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editIban, setEditIban] = useState("");
  const [accountId, setAccountId] = useState<number | typeof ACCOUNT_UNSET>(ACCOUNT_UNSET);
  const [accountMode, setAccountMode] = useState<typeof ACCOUNT_MODE_EXISTING | typeof ACCOUNT_MODE_CREATE>(ACCOUNT_MODE_EXISTING);
  const [file, setFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<typeof IMPORT_MODE_APPEND | typeof IMPORT_MODE_REPLACE>(IMPORT_MODE_APPEND);
  const [busy, setBusy] = useState(false);
  const [importPhase, setImportPhase] = useState<typeof IMPORT_PHASE_IDLE | typeof IMPORT_PHASE_IMPORTING | typeof IMPORT_PHASE_CATEGORIZING>(IMPORT_PHASE_IDLE);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [newAccountName, setNewAccountName] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const importPanelRef = useRef<HTMLDivElement | null>(null);
  const accountNameRef = useRef<HTMLInputElement | null>(null);

  const investmentAccounts = accounts.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
  const selectedInvestAccount = investmentAccounts.find((account) => account.id === investAccountId);
  const selectedAccount = accounts.find((account) => account.id === accountId);
  const overwrite = importMode === IMPORT_MODE_REPLACE;
  const showCreateAccount = accountMode === ACCOUNT_MODE_CREATE || accounts.length === 0;
  const canCreateDuringImport = showCreateAccount && Boolean(newAccountName.trim());
  const canImport = Boolean(file && !busy && (canCreateDuringImport || (!showCreateAccount && accountId !== ACCOUNT_UNSET)));

  async function loadAccounts() {
    const list = await api.accounts();
    setAccounts(list);
    if (list.length === 0) setAccountMode(ACCOUNT_MODE_CREATE);
    if (!balanceAccountId && list[0]) setBalanceAccountId(list[0].id);
    if (!setupMode && list.length === 1) setAccountId(list[0].id);
    else if (accountId !== ACCOUNT_UNSET && !list.some((account) => account.id === accountId)) setAccountId(ACCOUNT_UNSET);
    const investList = list.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
    if (investList.length === 1) setInvestAccountId(investList[0].id);
    else if (investAccountId !== "" && !investList.some((account) => account.id === investAccountId)) setInvestAccountId("");
  }

  async function saveEmployersIfAny() {
    const companies = parseEmployerNames(employerNames);
    if (companies.length === 0) return [];
    const result = await api.registerEmployers(companies);
    return result.companies;
  }

  async function createImportAccount(options?: { quiet?: boolean }) {
    const accountName = newAccountName.trim() || DEFAULT_CSV_ACCOUNT_NAME;
    setCreatingAccount(true);
    const created = await api.createAccount({ name: accountName, institution: DEFAULT_CSV_INSTITUTION, account_type: "checking", source: "csv", currency: "EUR" });
    setAccounts((current) => [...current, created]);
    setAccountId(created.id);
    setAccountMode(ACCOUNT_MODE_EXISTING);
    setNewAccountName("");
    if (user) markOnboardingComplete(user.id);
    if (setupMode) navigate(ACCOUNTS_PATH, { replace: true });
    if (!options?.quiet) {
      const companies = await saveEmployersIfAny();
      setMessageTone("ok");
      const employerNote = companies.length ? ` Employers saved: ${companies.join(", ")}.` : "";
      setMessage(`Created account “${created.name}”. You can import a CSV into it now.${employerNote}`);
    }
    setCreatingAccount(false);
    return created;
  }

  useEffect(() => {
    loadAccounts().catch((err: Error) => { setMessageTone("error"); setMessage(err.message); });
  }, [setupMode]);

  useEffect(() => {
    if (!setupMode) return;
    setAccountMode(ACCOUNT_MODE_CREATE);
    importPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => accountNameRef.current?.focus(), 280);
  }, [setupMode]);

  useEffect(() => {
    if (!busy) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timerId = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), TIMER_TICK_MS);
    return () => window.clearInterval(timerId);
  }, [busy]);

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    await api.createAccount({ name, institution, account_type: accountType, source: "manual", iban: iban || null });
    const companies = parseEmployerNames(employerNames);
    const employerNote = companies.length ? ` Employers saved: ${(await api.registerEmployers(companies)).companies.join(", ")}.` : "";
    setName("");
    setInstitution("");
    setIban("");
    setEmployerNames("");
    setMessageTone("ok");
    setMessage(`Account created.${employerNote}`);
    await loadAccounts();
  }

  async function createSnpAccount() {
    const created = await api.createAccount({
      name: DEFAULT_SNP_ACCOUNT_NAME,
      institution: DEFAULT_SNP_INSTITUTION,
      account_type: ACCOUNT_TYPE_INVESTMENT,
      source: "manual",
    });
    setInvestAccountId(created.id);
    setMessageTone("ok");
    setMessage(`Created “${created.name}”. Import investment history below.`);
    await loadAccounts();
  }

  async function saveBalance(event: FormEvent) {
    event.preventDefault();
    if (!balanceAccountId) return;
    await api.addBalance(Number(balanceAccountId), Number(balanceAmount));
    setBalanceAmount("");
    setMessageTone("ok");
    setMessage("Balance snapshot saved");
    await loadAccounts();
  }

  async function importInvestmentHistory(event: FormEvent) {
    event.preventDefault();
    if (!investFile || investAccountId === "") {
      setMessageTone("error");
      setMessage("Select an investment account and CSV file first.");
      return;
    }
    const replaceSnapshots = investMode === IMPORT_MODE_REPLACE;
    if (replaceSnapshots) {
      const confirmed = window.confirm(`Replace every balance snapshot on “${selectedInvestAccount?.name ?? "this account"}” with this CSV?`);
      if (!confirmed) return;
    }
    const result = await api.importInvestmentCsv(Number(investAccountId), investFile, replaceSnapshots);
    const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`];
    if (result.overwrite) parts.splice(1, 0, `replaced ${result.replaced}`);
    setMessageTone("ok");
    setMessage(`${parts.join(" · ")} → ${selectedInvestAccount?.name ?? "account"}`);
    setInvestFile(null);
    setInvestMode(IMPORT_MODE_APPEND);
    await loadAccounts();
  }

  function startEdit(account: Account) {
    setEditingId(account.id);
    setEditName(account.name);
    setEditIban(account.iban ?? "");
  }

  async function saveEdit(accountIdToSave: number) {
    await api.updateAccount(accountIdToSave, { name: editName, iban: editIban.trim() ? editIban : null });
    setEditingId(null);
    setMessageTone("ok");
    setMessage("Account updated. Matching transfers reclassified.");
    await api.classifyTransactions();
    await loadAccounts();
  }

  async function removeAccount(accountIdToRemove: number, label: string) {
    const confirmed = window.confirm(`Remove “${label}” and permanently delete all of its transactions and balances? This cannot be undone.`);
    if (!confirmed) return;
    await api.deleteAccount(accountIdToRemove);
    if (editingId === accountIdToRemove) setEditingId(null);
    if (balanceAccountId === accountIdToRemove) setBalanceAccountId("");
    if (investAccountId === accountIdToRemove) setInvestAccountId("");
    if (accountId === accountIdToRemove) setAccountId(ACCOUNT_UNSET);
    setMessageTone("ok");
    setMessage(`Removed “${label}” and deleted its transactions.`);
    await loadAccounts();
  }

  async function cancelImport() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setImportPhase(IMPORT_PHASE_IDLE);
    setMessageTone("ok");
    setMessage("Stopped waiting. Import may still finish on the server — refresh in a moment to check.");
    await loadAccounts();
  }

  async function onImport(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setMessageTone("error");
      setMessage(NEED_ACCOUNT_OR_NAME_MESSAGE);
      return;
    }
    let targetAccount = selectedAccount ?? null;
    let importAccountId = accountId === ACCOUNT_UNSET ? null : accountId;
    if (showCreateAccount || importAccountId === null) {
      if (!newAccountName.trim()) {
        setMessageTone("error");
        setMessage(NEED_ACCOUNT_OR_NAME_MESSAGE);
        return;
      }
      targetAccount = await createImportAccount({ quiet: true });
      importAccountId = targetAccount.id;
    }
    if (overwrite) {
      const confirmed = window.confirm(`Replace every transaction on “${targetAccount?.name ?? "this account"}” with this file? Existing rows on that account will be deleted.`);
      if (!confirmed) return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setImportPhase(IMPORT_PHASE_IMPORTING);
    setMessage("");
    setMessageTone("");
    const companies = await saveEmployersIfAny();
    const result = await api.importCsv(importAccountId, file, overwrite, controller.signal);
    const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`];
    if (result.overwrite) parts.push(`replaced ${result.replaced}`);
    if (result.categorized > 0) parts.push(`${result.categorized} matched by rules`);
    if (companies.length) parts.push(`wages from ${companies.join(", ")}`);
    setImportPhase(IMPORT_PHASE_CATEGORIZING);
    const classifyResult = await api.classifyTransactions(importAccountId, controller.signal);
    parts.push(`categorized ${classifyResult.categorized}`);
    setMessageTone("ok");
    setMessage(`${parts.join(" · ")} → ${targetAccount?.name ?? "account"}`);
    setFile(null);
    setImportMode(IMPORT_MODE_APPEND);
    await loadAccounts();
    abortRef.current = null;
    setImportPhase(IMPORT_PHASE_IDLE);
    setBusy(false);
  }

  return (
    <div>
      <section className="hero">
        <h1>Accounts File Connection</h1>
        <p>Create accounts and connect them with bank CSV/Excel files. Manage balances and investment history here.</p>
      </section>

      <div ref={importPanelRef} data-tour="csv-import" className={`panel csv-import${busy ? " is-busy" : ""}${setupMode ? " is-setup" : ""}`} style={{ marginBottom: "1rem" }}>
        <div className="csv-import-head">
          <div>
            <h2>Import bank CSV/Excel</h2>
            <p className="muted">Create or pick an account, then load a bank export. Rows import first; categories are assigned next.</p>
          </div>
        </div>

        <form className="csv-import-form" onSubmit={(e) => onImport(e).catch((err: unknown) => { abortRef.current = null; setBusy(false); setCreatingAccount(false); setImportPhase(IMPORT_PHASE_IDLE); const aborted = err instanceof DOMException && err.name === "AbortError"; setMessageTone(aborted ? "ok" : "error"); setMessage(aborted ? "Stopped waiting. Refresh to see what finished." : err instanceof Error ? err.message : String(err)); })}>
          <div className="csv-step">
            <span className="csv-step-num" aria-hidden="true">1</span>
            <div className="csv-step-body">
              <span className="csv-label">Account</span>
              <span className="csv-hint">Which account should receive these transactions?</span>
              {accounts.length > 0 && (
                <div className="csv-account-mode" role="group" aria-label="Account source">
                  <button type="button" className={`csv-account-mode-btn${accountMode === ACCOUNT_MODE_EXISTING ? " is-selected" : ""}`} disabled={busy} onClick={() => setAccountMode(ACCOUNT_MODE_EXISTING)}>{USE_EXISTING_LABEL}</button>
                  <button type="button" className={`csv-account-mode-btn${accountMode === ACCOUNT_MODE_CREATE ? " is-selected" : ""}`} disabled={busy} onClick={() => setAccountMode(ACCOUNT_MODE_CREATE)}>{CREATE_NEW_LABEL}</button>
                </div>
              )}
              {showCreateAccount ? (
                <div className="csv-create-account">
                  <p className="csv-empty">{accounts.length === 0 ? EMPTY_ACCOUNTS_HINT : CREATE_ACCOUNT_HINT}</p>
                  <div className="csv-create-row">
                    <input ref={accountNameRef} value={newAccountName} onChange={(e) => setNewAccountName(e.target.value)} placeholder={ACCOUNT_NAME_PLACEHOLDER} disabled={busy || creatingAccount} required />
                    <button type="button" className="secondary" disabled={busy || creatingAccount || !newAccountName.trim()} onClick={() => createImportAccount().catch((err: Error) => { setCreatingAccount(false); setMessageTone("error"); setMessage(err.message); })}>{creatingAccount ? CREATING_ACCOUNT_LABEL : CREATE_ACCOUNT_LABEL}</button>
                  </div>
                </div>
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
              <span className="csv-label">Employers / salary companies</span>
              <span className="csv-hint">Names that pay your wage (comma-separated). Matching inflows become Income; other positives become Transfers.</span>
              <input value={employerNames} onChange={(e) => setEmployerNames(e.target.value)} placeholder={EMPLOYER_PLACEHOLDER} disabled={busy} />
            </span>
          </label>

          <label className="csv-step">
            <span className="csv-step-num" aria-hidden="true">3</span>
            <span className="csv-step-body">
              <span className="csv-label">CSV/Excel file</span>
              <span className="csv-hint">Export from your bank, then choose the file here.</span>
              <span className={`csv-file${file ? " has-file" : ""}`}>
                <input type="file" accept=".csv,.xls,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required disabled={busy} />
                <span className="csv-file-name">{file ? file.name : "No file chosen"}</span>
                <span className="csv-file-action">{file ? "Change file" : "Choose file"}</span>
              </span>
            </span>
          </label>

          <fieldset className="csv-step csv-mode" disabled={busy}>
            <span className="csv-step-num" aria-hidden="true">4</span>
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
            <button type="submit" disabled={!canImport}>{busy ? (importPhase === IMPORT_PHASE_IMPORTING ? "Importing…" : "Categorizing…") : "Import and categorize"}</button>
            {busy && (
              <button type="button" className="secondary" onClick={() => cancelImport().catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>Cancel</button>
            )}
            {selectedAccount && file && !busy && (
              <p className="csv-summary muted">
                {overwrite ? "Replace" : "Add to"} <strong>{selectedAccount.name}</strong> from <strong>{file.name}</strong>
              </p>
            )}
          </div>
        </form>

        {message && <p className={`csv-status csv-status-${messageTone || "ok"}`}>{message}</p>}
        {busy && (
          <div className="categorize-overlay" role="status" aria-live="polite">
            <div className="categorize-card">
              <div className="categorize-ring" aria-hidden="true">
                <span className="categorize-ring-spin" />
                <span className="categorize-ring-time">{formatElapsed(elapsedSeconds)}</span>
              </div>
              <h3>{importPhase === IMPORT_PHASE_IMPORTING ? "Importing transactions" : "Categorizing your expenses"}</h3>
              <p className="muted">{importPhase === IMPORT_PHASE_IMPORTING ? "Saving rows from your file. This step is usually quick." : "Matching merchants to categories. You can cancel waiting — the server may still finish in the background."}</p>
            </div>
          </div>
        )}
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
                        <button type="button" onClick={() => saveEdit(a.id).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>Save</button>
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
                        <button type="button" className="secondary" onClick={() => removeAccount(a.id, a.name).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>Remove</button>
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
          <form className="form" onSubmit={(e) => createAccount(e).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>
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
          <button type="button" className="secondary" style={{ marginTop: "0.75rem" }} onClick={() => createSnpAccount().catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>
            Add S&amp;P 500 investment
          </button>
          <h3 style={{ marginTop: "1.5rem" }}>Record balance</h3>
          <form className="form" onSubmit={(e) => saveBalance(e).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>
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
          <form className="form" onSubmit={(e) => importInvestmentHistory(e).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })}>
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
        </div>
      </div>
    </div>
  );
}
