import { useEffect, useRef, useState } from "react";
import { api, type AccountFlow, type Category, type Transaction } from "../api";
import { MoneyFlowGraph } from "../components/MoneyFlowGraph";
import { amountClass, amountTone, euro, ledgerAmountTone, ledgerDisplayAmount, portionKind } from "../format";

const IMPORT_PHASE_IDLE = "idle";
const IMPORT_PHASE_CATEGORIZING = "categorizing";
const TIMER_TICK_MS = 250;
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
const CATEGORIZE_BUTTON_LABEL = "Categorize";
const CATEGORIZING_BUTTON_LABEL = "Categorizing…";
const CATEGORIZE_DONE_MESSAGE = (count: number) => (count === 1 ? "Categorized 1 transaction." : `Categorized ${count} transactions.`);
const CATEGORIZE_NONE_MESSAGE = "No uncategorized transactions matched rules or AI.";
const FLOW_MONTH_LOOKBACK = 24;
const FLOW_MONTH_LOCALE = "en-US";

type SplitDraft = { label: string; amount: string; category_id: number | "" };
type LedgerMonthOption = { value: string; label: string };
type FlowMonthOption = { year: number; month: number; value: string; label: string };

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

function buildFlowMonthOptions(): FlowMonthOption[] {
  const options: FlowMonthOption[] = [];
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

const LEDGER_MONTH_OPTIONS = buildLedgerMonthOptions();
const FLOW_MONTH_OPTIONS = buildFlowMonthOptions();

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
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [onlyUncategorized, setOnlyUncategorized] = useState(false);
  const [ledgerMonth, setLedgerMonth] = useState(currentLedgerMonthKey);
  const [ledgerSearch, setLedgerSearch] = useState("");
  const [ledgerSearchQuery, setLedgerSearchQuery] = useState("");
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "error" | "">("");
  const [busy, setBusy] = useState(false);
  const [importPhase, setImportPhase] = useState<typeof IMPORT_PHASE_IDLE | typeof IMPORT_PHASE_CATEGORIZING>(IMPORT_PHASE_IDLE);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const [splittingId, setSplittingId] = useState<number | null>(null);
  const [splitDrafts, setSplitDrafts] = useState<SplitDraft[]>([]);
  const [splitBusy, setSplitBusy] = useState(false);
  const [flowMonth, setFlowMonth] = useState(FLOW_MONTH_OPTIONS[0]?.value ?? "");
  const [flow, setFlow] = useState<AccountFlow | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);

  const splittingTx = transactions.find((tx) => tx.id === splittingId) ?? null;
  const draftTotal = splitDrafts.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
  const splitTarget = splittingTx ? Math.abs(splittingTx.amount) : 0;
  const splitBalanced = Math.abs(draftTotal - splitTarget) < SPLIT_BALANCE_TOLERANCE;
  const splitRemaining = Math.round((splitTarget - draftTotal) * 100) / 100;
  const selectedFlowMonth = FLOW_MONTH_OPTIONS.find((option) => option.value === flowMonth) ?? FLOW_MONTH_OPTIONS[0];

  async function load() {
    const txQuery: { uncategorized?: boolean; year?: number; month?: number; q?: string } = { uncategorized: onlyUncategorized };
    if (ledgerSearchQuery) txQuery.q = ledgerSearchQuery;
    else if (ledgerMonth !== LEDGER_MONTH_ALL) {
      const [year, month] = ledgerMonth.split("-").map(Number);
      txQuery.year = year;
      txQuery.month = month;
    }
    const [txs, cats] = await Promise.all([api.transactions(txQuery), api.categories()]);
    setTransactions(txs);
    setCategories(cats);
  }

  async function loadFlow(year: number, month: number) {
    setFlowLoading(true);
    const next = await api.accountFlow(year, month);
    setFlow(next);
    setFlowLoading(false);
  }

  async function refreshFlow() {
    if (selectedFlowMonth) await loadFlow(selectedFlowMonth.year, selectedFlowMonth.month);
  }

  useEffect(() => {
    const trimmed = ledgerSearch.trim();
    const timerId = window.setTimeout(() => setLedgerSearchQuery(trimmed), LEDGER_SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timerId);
  }, [ledgerSearch]);

  useEffect(() => {
    load().catch((err: Error) => { setMessageTone("error"); setMessage(err.message); });
  }, [onlyUncategorized, ledgerMonth, ledgerSearchQuery]);

  useEffect(() => {
    if (!selectedFlowMonth) return;
    setFlowLoading(true);
    api.accountFlow(selectedFlowMonth.year, selectedFlowMonth.month)
      .then(setFlow)
      .catch((err: Error) => { setMessageTone("error"); setMessage(err.message); })
      .then(() => setFlowLoading(false));
  }, [flowMonth]);

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
    await refreshFlow();
    abortRef.current = null;
    setImportPhase(IMPORT_PHASE_IDLE);
    setBusy(false);
  }

  async function saveGraphIban(accountId: number, nextIban: string | null) {
    await api.updateAccount(accountId, { iban: nextIban });
    setMessageTone("ok");
    setMessage("IBAN saved. Matching transfers reclassified.");
    await api.classifyTransactions();
    await load();
    await refreshFlow();
  }

  async function quickAddAccount(input: { name: string; iban: string | null; account_type: string }) {
    await api.createAccount({ name: input.name, iban: input.iban, account_type: input.account_type, source: "manual" });
    setMessageTone("ok");
    setMessage(`Added “${input.name}”.`);
    await load();
    await refreshFlow();
  }

  async function removeAccount(accountId: number, label: string) {
    const confirmed = window.confirm(`Remove “${label}” and permanently delete all of its transactions and balances? This cannot be undone.`);
    if (!confirmed) return;
    await api.deleteAccount(accountId);
    setMessageTone("ok");
    setMessage(`Removed “${label}” and deleted its transactions.`);
    await load();
    await refreshFlow();
  }

  return (
    <div>
      <section className="hero">
        <h1>Transactions</h1>
        <p>See money flow, then classify spending, split shared bills, and grow rules from one-click assigns.</p>
      </section>

      <div className="panel flow-panel" data-tour="money-flow">
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
          onSaveIban={(accountId, nextIban) => saveGraphIban(accountId, nextIban).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); throw err; })}
          onAddAccount={(input) => quickAddAccount(input).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); throw err; })}
          onRemoveAccount={(accountId, label) => removeAccount(accountId, label).catch((err: Error) => { setMessageTone("error"); setMessage(err.message); throw err; })}
        />
      </div>

      {message && <p className={`csv-status csv-status-${messageTone || "ok"}`} style={{ marginBottom: "1rem" }}>{message}</p>}

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
              <h3>Categorizing your expenses</h3>
              <p className="muted">Matching merchants to categories. You can cancel waiting — the server may still finish in the background.</p>
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
