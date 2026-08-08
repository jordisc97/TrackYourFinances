import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type Account, type Category, type Transaction } from "../api";
import { useAuth } from "../auth";
import { markOnboardingComplete } from "../components/ProductTour";
import { amountClass, amountTone, euro, ledgerAmountTone, ledgerDisplayAmount, parseEmployerNames, portionKind } from "../format";

const ACCOUNT_UNSET = "" as const;
const IMPORT_PHASE_IDLE = "idle";
const IMPORT_PHASE_IMPORTING = "importing";
const IMPORT_PHASE_CATEGORIZING = "categorizing";
const TIMER_TICK_MS = 250;
const IMPORT_MODE_APPEND = "append";
const IMPORT_MODE_REPLACE = "replace";
const ACCOUNT_MODE_EXISTING = "existing";
const ACCOUNT_MODE_CREATE = "create";
const DEFAULT_CSV_ACCOUNT_NAME = "CSV checking";
const DEFAULT_CSV_INSTITUTION = "CSV import";
const ACCOUNT_NAME_PLACEHOLDER = "e.g. Everyday checking";
const SETUP_QUERY_KEY = "setup";
const SETUP_QUERY_VALUE = "1";
const TRANSACTIONS_PATH = "/transactions";
const EMPLOYER_PLACEHOLDER = "PayPal, HP, …";
const DEFAULT_PORTION_A_LABEL = "Me";
const DEFAULT_PORTION_B_LABEL = "Partner";
const LEDGER_MONTH_ALL = "all";
const LEDGER_MONTH_LOOKBACK = 36;
const LEDGER_MONTH_LOCALE = "en-US";
const LEDGER_MONTH_ALL_LABEL = "All months";
const LEDGER_SEARCH_DEBOUNCE_MS = 300;
const LEDGER_SEARCH_LABEL = "Search";
const LEDGER_SEARCH_PLACEHOLDER = "Merchant or description…";
const SPLIT_MATCH_MESSAGE = "Nice math skills";
const SPLIT_BALANCE_TOLERANCE = 0.02;
const USE_EXISTING_LABEL = "Use existing";
const CREATE_NEW_LABEL = "Create new";
const CREATE_ACCOUNT_HINT = "Name the new account. Import will create it, then load your file.";
const EMPTY_ACCOUNTS_HINT = "No accounts yet. Type a name below, choose your file, then Import and categorize.";
const NEED_ACCOUNT_OR_NAME_MESSAGE = "Name a new account or select an existing one, and choose a CSV/Excel file before importing.";
const CREATE_ACCOUNT_LABEL = "Create account";
const CREATING_ACCOUNT_LABEL = "Creating…";
const CATEGORIZE_BUTTON_LABEL = "Categorize";
const CATEGORIZING_BUTTON_LABEL = "Categorizing…";
const CATEGORIZE_DONE_MESSAGE = (count: number) => (count === 1 ? "Categorized 1 transaction." : `Categorized ${count} transactions.`);
const CATEGORIZE_NONE_MESSAGE = "No uncategorized transactions matched rules or AI.";

type SplitDraft = { label: string; amount: string; category_id: number | "" };
type LedgerMonthOption = { value: string; label: string };

function currentLedgerMonthKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function buildLedgerMonthOptions(): LedgerMonthOption[] {
  const options: LedgerMonthOption[] = [{ value: LEDGER_MONTH_ALL, label: LEDGER_MONTH_ALL_LABEL }];
  const cursor = new Date();
  cursor.setDate(1);
  for (let i = 0; i < LEDGER_MONTH_LOOKBACK; i++) {
    options.push({
      value: `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`,
      label: cursor.toLocaleDateString(LEDGER_MONTH_LOCALE, { month: "short", year: "numeric" }),
    });
    cursor.setMonth(cursor.getMonth() - 1);
  }
  return options;
}

const LEDGER_MONTH_OPTIONS = buildLedgerMonthOptions();

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function defaultDrafts(tx: Transaction): SplitDraft[] {
  const half = Math.round((Math.abs(tx.amount) / 2) * 100) / 100;
  const rest = Math.round((Math.abs(tx.amount) - half) * 100) / 100;
  const categoryId = tx.category_id ?? "";
  if (tx.splits && tx.splits.length >= 2) {
    return tx.splits.map((s) => ({ label: s.label, amount: String(Math.abs(s.amount)), category_id: s.category_id ?? categoryId }));
  }
  return [
    { label: DEFAULT_PORTION_A_LABEL, amount: String(half), category_id: categoryId },
    { label: DEFAULT_PORTION_B_LABEL, amount: String(rest), category_id: categoryId },
  ];
}

export function TransactionsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setupMode = searchParams.get(SETUP_QUERY_KEY) === SETUP_QUERY_VALUE;
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [onlyUncategorized, setOnlyUncategorized] = useState(false);
  const [ledgerMonth, setLedgerMonth] = useState(currentLedgerMonthKey);
  const [ledgerSearch, setLedgerSearch] = useState("");
  const [ledgerSearchQuery, setLedgerSearchQuery] = useState("");
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "error" | "">("");
  const [accountId, setAccountId] = useState<number | typeof ACCOUNT_UNSET>(ACCOUNT_UNSET);
  const [accountMode, setAccountMode] = useState<typeof ACCOUNT_MODE_EXISTING | typeof ACCOUNT_MODE_CREATE>(ACCOUNT_MODE_EXISTING);
  const [file, setFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<typeof IMPORT_MODE_APPEND | typeof IMPORT_MODE_REPLACE>(IMPORT_MODE_APPEND);
  const [busy, setBusy] = useState(false);
  const [importPhase, setImportPhase] = useState<typeof IMPORT_PHASE_IDLE | typeof IMPORT_PHASE_IMPORTING | typeof IMPORT_PHASE_CATEGORIZING>(IMPORT_PHASE_IDLE);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const importPanelRef = useRef<HTMLDivElement | null>(null);
  const accountNameRef = useRef<HTMLInputElement | null>(null);
  const [newAccountName, setNewAccountName] = useState("");
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [employerNames, setEmployerNames] = useState("");
  const [splittingId, setSplittingId] = useState<number | null>(null);
  const [splitDrafts, setSplitDrafts] = useState<SplitDraft[]>([]);
  const [splitBusy, setSplitBusy] = useState(false);

  const selectedAccount = accounts.find((account) => account.id === accountId);
  const overwrite = importMode === IMPORT_MODE_REPLACE;
  const showCreateAccount = accountMode === ACCOUNT_MODE_CREATE || accounts.length === 0;
  const canCreateDuringImport = showCreateAccount && Boolean(newAccountName.trim());
  const canImport = Boolean(file && !busy && (canCreateDuringImport || (!showCreateAccount && accountId !== ACCOUNT_UNSET)));
  const splittingTx = transactions.find((tx) => tx.id === splittingId) ?? null;
  const draftTotal = splitDrafts.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
  const splitTarget = splittingTx ? Math.abs(splittingTx.amount) : 0;
  const splitBalanced = Math.abs(draftTotal - splitTarget) < SPLIT_BALANCE_TOLERANCE;
  const splitRemaining = Math.round((splitTarget - draftTotal) * 100) / 100;

  async function load() {
    const txQuery: { uncategorized?: boolean; year?: number; month?: number; q?: string } = { uncategorized: onlyUncategorized };
    if (ledgerSearchQuery) txQuery.q = ledgerSearchQuery;
    else if (ledgerMonth !== LEDGER_MONTH_ALL) {
      const [year, month] = ledgerMonth.split("-").map(Number);
      txQuery.year = year;
      txQuery.month = month;
    }
    const [txs, cats, accs] = await Promise.all([api.transactions(txQuery), api.categories(), api.accounts()]);
    setTransactions(txs);
    setCategories(cats);
    setAccounts(accs);
    if (accs.length === 0) setAccountMode(ACCOUNT_MODE_CREATE);
    if (!setupMode && accs.length === 1) setAccountId(accs[0].id);
    else if (accountId !== ACCOUNT_UNSET && !accs.some((account) => account.id === accountId)) setAccountId(ACCOUNT_UNSET);
  }

  async function saveEmployersIfAny() {
    const companies = parseEmployerNames(employerNames);
    if (companies.length === 0) return [];
    const result = await api.registerEmployers(companies);
    return result.companies;
  }

  async function createImportAccount(options?: { quiet?: boolean }) {
    const name = newAccountName.trim() || DEFAULT_CSV_ACCOUNT_NAME;
    setCreatingAccount(true);
    const created = await api.createAccount({ name, institution: DEFAULT_CSV_INSTITUTION, account_type: "checking", source: "csv", currency: "EUR" });
    setAccounts((current) => [...current, created]);
    setAccountId(created.id);
    setAccountMode(ACCOUNT_MODE_EXISTING);
    setNewAccountName("");
    if (user) markOnboardingComplete(user.id);
    if (setupMode) navigate(TRANSACTIONS_PATH, { replace: true });
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
    const trimmed = ledgerSearch.trim();
    const timerId = window.setTimeout(() => setLedgerSearchQuery(trimmed), LEDGER_SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timerId);
  }, [ledgerSearch]);

  useEffect(() => {
    load().catch((err: Error) => { setMessageTone("error"); setMessage(err.message); });
  }, [onlyUncategorized, ledgerMonth, ledgerSearchQuery, setupMode]);

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

  async function assign(txId: number, categoryId: number) {
    await api.assignCategory(txId, { category_id: categoryId, create_rule: true });
    await load();
  }

  function openSplit(tx: Transaction) {
    setSplittingId(tx.id);
    setSplitDrafts(defaultDrafts(tx));
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-split-anchor="${tx.id}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }

  function updateDraft(index: number, patch: Partial<SplitDraft>) {
    setSplitDrafts((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function saveSplit() {
    if (!splittingTx || !splitBalanced) return;
    setSplitBusy(true);
    const portions = splitDrafts.map((row) => ({
      amount: Number(row.amount) || 0,
      label: row.label.trim() || "Share",
      category_id: row.category_id === "" ? splittingTx.category_id : Number(row.category_id),
    }));
    await api.splitTransaction(splittingTx.id, portions);
    setSplittingId(null);
    setSplitDrafts([]);
    setMessageTone("ok");
    setMessage(`Split saved for ${splittingTx.merchant || splittingTx.raw_description || "transaction"}.`);
    await load();
    setSplitBusy(false);
  }

  async function clearSplit(txId: number) {
    setSplitBusy(true);
    await api.unsplitTransaction(txId);
    if (splittingId === txId) {
      setSplittingId(null);
      setSplitDrafts([]);
    }
    setMessageTone("ok");
    setMessage("Split removed.");
    await load();
    setSplitBusy(false);
  }

  async function cancelImport() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setImportPhase(IMPORT_PHASE_IDLE);
    setMessageTone("ok");
    setMessage("Stopped waiting. Import may still finish on the server — refresh the ledger in a moment to check.");
    await load();
  }

  async function categorizeLedger() {
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setImportPhase(IMPORT_PHASE_CATEGORIZING);
    setMessage("");
    setMessageTone("");
    const result = await api.classifyTransactions(undefined, controller.signal);
    setMessageTone("ok");
    setMessage(result.categorized > 0 ? CATEGORIZE_DONE_MESSAGE(result.categorized) : CATEGORIZE_NONE_MESSAGE);
    await load();
    abortRef.current = null;
    setImportPhase(IMPORT_PHASE_IDLE);
    setBusy(false);
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
    await load();
    abortRef.current = null;
    setImportPhase(IMPORT_PHASE_IDLE);
    setBusy(false);
  }

  return (
    <div>
      <section className="hero">
        <h1>Transactions</h1>
        <p>Classify spending, split shared bills, import bank CSVs, and grow rules from one-click assigns.</p>
      </section>

      <div ref={importPanelRef} data-tour="csv-import" className={`panel csv-import${busy ? " is-busy" : ""}${setupMode ? " is-setup" : ""}`} style={{ marginBottom: "1rem" }}>
        <div className="csv-import-head">
          <div>
            <h2>Import bank CSV/Excel</h2>
            <p className="muted">Bank column names are mapped automatically. Rows import first, then categories are assigned in a separate step.</p>
          </div>
        </div>

        <form className="csv-import-form" onSubmit={(e) => onImport(e).catch((err: unknown) => { abortRef.current = null; setBusy(false); setCreatingAccount(false); setImportPhase(IMPORT_PHASE_IDLE); const aborted = err instanceof DOMException && err.name === "AbortError"; setMessageTone(aborted ? "ok" : "error"); setMessage(aborted ? "Stopped waiting. Refresh the ledger to see what finished." : err instanceof Error ? err.message : String(err)); })}>
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
      </div>

      <div className={`panel ledger-panel${busy ? " is-busy" : ""}`}>
        <div className="row ledger-toolbar" style={{ marginBottom: "0.75rem" }}>
          <h2 style={{ flex: 2 }}>Ledger</h2>
          <label className="ledger-month-filter">
            <span className="muted">Month</span>
            <select value={ledgerMonth} onChange={(e) => setLedgerMonth(e.target.value)} disabled={busy}>
              {LEDGER_MONTH_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="ledger-search-filter">
            <span className="muted">{LEDGER_SEARCH_LABEL}</span>
            <input type="search" value={ledgerSearch} onChange={(e) => setLedgerSearch(e.target.value)} placeholder={LEDGER_SEARCH_PLACEHOLDER} disabled={busy} />
          </label>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input type="checkbox" checked={onlyUncategorized} onChange={(e) => setOnlyUncategorized(e.target.checked)} disabled={busy} />
            Uncategorized inbox
          </label>
          <button
            type="button"
            className="ledger-categorize-btn"
            disabled={busy}
            onClick={() => categorizeLedger().catch((err: unknown) => { abortRef.current = null; setBusy(false); setImportPhase(IMPORT_PHASE_IDLE); const aborted = err instanceof DOMException && err.name === "AbortError"; setMessageTone(aborted ? "ok" : "error"); setMessage(aborted ? "Stopped waiting. Refresh the ledger to see what finished." : err instanceof Error ? err.message : String(err)); })}
          >
            {busy && importPhase === IMPORT_PHASE_CATEGORIZING ? CATEGORIZING_BUTTON_LABEL : CATEGORIZE_BUTTON_LABEL}
          </button>
          <span className="muted">{transactions.length >= 200 ? "Showing latest 200" : `${transactions.length} shown`}</span>
        </div>
        <div className={`ledger-body${busy ? " is-obscured" : ""}`}>
          <table className="table">
            <thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th>Assign</th><th>Split</th></tr></thead>
            <tbody>
              {transactions.map((tx) => (
                <FragmentRow
                  key={tx.id}
                  tx={tx}
                  categories={categories}
                  busy={busy || splitBusy}
                  splitting={splittingId === tx.id}
                  splitDrafts={splittingId === tx.id ? splitDrafts : []}
                  splitBalanced={splitBalanced}
                  draftTotal={draftTotal}
                  splitTarget={splitTarget}
                  splitRemaining={splitRemaining}
                  onAssign={assign}
                  onOpenSplit={openSplit}
                  onClearSplit={clearSplit}
                  onCancelSplit={() => { setSplittingId(null); setSplitDrafts([]); }}
                  onUpdateDraft={updateDraft}
                  onAddPortion={() => setSplitDrafts((rows) => [...rows, { label: "Share", amount: "0", category_id: tx.category_id ?? "" }])}
                  onSaveSplit={() => saveSplit().catch((err: Error) => { setSplitBusy(false); setMessageTone("error"); setMessage(err.message); })}
                  onError={(err) => { setMessageTone("error"); setMessage(err); }}
                />
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
              <h3>{importPhase === IMPORT_PHASE_IMPORTING ? "Importing transactions" : "Categorizing your expenses"}</h3>
              <p className="muted">{importPhase === IMPORT_PHASE_IMPORTING ? "Saving rows from your file. This step is usually quick." : "Matching merchants to categories. You can cancel waiting — the server may still finish in the background."}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FragmentRow({
  tx, categories, busy, splitting, splitDrafts, splitBalanced, draftTotal, splitTarget, splitRemaining,
  onAssign, onOpenSplit, onClearSplit, onCancelSplit, onUpdateDraft, onAddPortion, onSaveSplit, onError,
}: {
  tx: Transaction;
  categories: Category[];
  busy: boolean;
  splitting: boolean;
  splitDrafts: SplitDraft[];
  splitBalanced: boolean;
  draftTotal: number;
  splitTarget: number;
  splitRemaining: number;
  onAssign: (txId: number, categoryId: number) => Promise<void>;
  onOpenSplit: (tx: Transaction) => void;
  onClearSplit: (txId: number) => Promise<void>;
  onCancelSplit: () => void;
  onUpdateDraft: (index: number, patch: Partial<SplitDraft>) => void;
  onAddPortion: () => void;
  onSaveSplit: () => void;
  onError: (message: string) => void;
}) {
  return (
    <>
      <tr data-split-anchor={tx.id}>
        <td>{tx.booked_at}</td>
        <td>
          <div>{tx.merchant || tx.raw_description || "—"}</div>
          {(tx.location || (tx.counterparty && tx.counterparty !== tx.merchant)) && (
            <div className="muted" style={{ fontSize: "0.85em" }}>
              {[tx.location, tx.counterparty && tx.counterparty !== tx.merchant ? (tx.amount < 0 ? `To ${tx.counterparty}` : `From ${tx.counterparty}`) : null].filter(Boolean).join(" · ")}
            </div>
          )}
          {tx.splits && tx.splits.length > 0 && !splitting && <span className="pill" style={{ marginLeft: "0.4rem" }}>Split</span>}
        </td>
        <td className={amountClass(ledgerAmountTone(tx))}>{euro.format(ledgerDisplayAmount(tx))}</td>
        <td>{tx.category_name || <span className="pill warn">Uncategorized</span>}</td>
        <td>
          <select defaultValue="" disabled={busy} onChange={(e) => { const value = Number(e.target.value); if (value) onAssign(tx.id, value).catch((err: Error) => onError(err.message)); }}>
            <option value="" disabled>Choose…</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </td>
        <td>
          <div className="row" style={{ gap: "0.35rem", minWidth: "7rem" }}>
            <button type="button" className="secondary" disabled={busy || tx.amount === 0} onClick={() => onOpenSplit(tx)}>{splitting ? "Editing…" : "Split"}</button>
            {tx.splits && tx.splits.length > 0 && !splitting && (
              <button type="button" className="secondary" disabled={busy} onClick={() => onClearSplit(tx.id).catch((err: Error) => onError(err.message))}>Clear</button>
            )}
          </div>
        </td>
      </tr>
      {splitting && (
        <tr className="split-editor-row">
          <td colSpan={6}>
            <div className="split-editor-inline panel">
              <div className="row" style={{ marginBottom: "0.75rem" }}>
                <div style={{ flex: 2 }}>
                  <h2 style={{ marginBottom: "0.25rem" }}>Split bill</h2>
                  <p className="muted">{tx.merchant || tx.raw_description || "Transaction"} · {euro.format(tx.amount)}</p>
                </div>
                <button type="button" className="secondary" disabled={busy} onClick={onCancelSplit}>Cancel</button>
              </div>
              <div className="split">
                {splitDrafts.map((row, index) => (
                  <div className="split-row" key={index}>
                    <input value={row.label} onChange={(e) => onUpdateDraft(index, { label: e.target.value })} placeholder="Label" disabled={busy} />
                    <input type="number" min={0} step="0.01" value={row.amount} onChange={(e) => onUpdateDraft(index, { amount: e.target.value })} placeholder="Amount" disabled={busy} />
                    <select value={row.category_id} onChange={(e) => onUpdateDraft(index, { category_id: e.target.value ? Number(e.target.value) : "" })} disabled={busy}>
                      <option value="">Same category</option>
                      {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <div className="row" style={{ marginTop: "0.85rem", alignItems: "center" }}>
                <p className={splitBalanced ? "csv-status-ok" : "csv-status-error"} style={{ flex: 2, margin: 0, background: "transparent", padding: 0 }}>
                  {splitBalanced
                    ? `Portions ${euro.format(draftTotal)} / ${euro.format(splitTarget)} — ${SPLIT_MATCH_MESSAGE}`
                    : `Portions ${euro.format(draftTotal)} / ${euro.format(splitTarget)} — ${euro.format(Math.abs(splitRemaining))} ${splitRemaining > 0 ? "remaining" : "over"}`}
                </p>
                <button type="button" className="secondary" disabled={busy} onClick={onAddPortion}>Add portion</button>
                <button type="button" disabled={busy || !splitBalanced || splitDrafts.length < 2} onClick={onSaveSplit}>{busy ? "Saving…" : "Save split"}</button>
              </div>
            </div>
          </td>
        </tr>
      )}
      {!splitting && tx.splits?.map((split) => (
        <tr key={`${tx.id}-${split.id}`} className="split-portion-row">
          <td />
          <td className="muted">↳ {split.label}</td>
          <td className={amountClass(amountTone(split.amount, portionKind(split, tx)))}>{euro.format(split.amount)}</td>
          <td className="muted">{split.category_name || tx.category_name || "—"}</td>
          <td colSpan={2} />
        </tr>
      ))}
    </>
  );
}
