import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type CategorySpend, type Dashboard, type InvestmentMonthRow, type MonthNavRow, type SeriesPoint, type Transaction, type YearlyObjective } from "../api";
import { AdvisorChat } from "../components/AdvisorChat";
import { amountClass, amountTone, axisMoney, euro, portionKind, signedEuro, whole } from "../format";

const ACCOUNT_TYPE_INVESTMENT = "investment";
const PCT_TOTAL_TARGET = 100;

function themeColor(token: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
}

function toTimeSeries(points: SeriesPoint[]) {
  return points.map((point) => {
    const [year, month] = point.label.split("-").map(Number);
    return { value: point.value, at: Date.UTC(year, month - 1, 1), label: point.label, kind: point.kind };
  });
}

function formatAxisDate(ms: number) {
  return new Date(ms).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function CombinedWealthPanel({ title, historical, forecast, forecastNoInvest, color, forecastColor, note, objectives, onSaveTarget }: {
  title: string; historical: SeriesPoint[]; forecast: SeriesPoint[]; forecastNoInvest: SeriesPoint[];
  color: string; forecastColor: string; note?: string; objectives: YearlyObjective[];
  onSaveTarget: (year: number, target: number) => Promise<void>;
}) {
  const histSeries = toTimeSeries(historical);
  const fcstSeries = toTimeSeries(forecast).filter((p) => p.kind === "projected");
  const noInvSeries = toTimeSeries(forecastNoInvest).filter((p) => p.kind === "projected");
  const bridge = histSeries.length > 0 ? histSeries[histSeries.length - 1] : null;
  const merged = [
    ...histSeries.map((p) => ({ at: p.at, historical: p.value, forecast: undefined as number | undefined, noInvest: undefined as number | undefined })),
    ...(bridge ? [{ at: bridge.at, historical: undefined as number | undefined, forecast: bridge.value, noInvest: bridge.value }] : []),
    ...fcstSeries.map((p, i) => ({ at: p.at, historical: undefined as number | undefined, forecast: p.value, noInvest: noInvSeries[i]?.value })),
  ];
  const muted = themeColor("--muted");
  const track = themeColor("--track");
  const panel = themeColor("--panel-solid");
  const ink = themeColor("--ink");
  const line = themeColor("--line");
  const tipStyle = { background: panel, border: `1px solid ${line}`, borderRadius: 12, color: ink, boxShadow: "var(--shadow)" };
  return (
    <div className="panel wealth-split-panel">
      <h2>{title}</h2>
      {note && <p className="muted chart-note">{note}</p>}
      <div className="wealth-split">
        <div className="wealth-split-chart">
          <div className="chart-frame">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={merged} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={track} />
                <XAxis dataKey="at" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={formatAxisDate} minTickGap={28} tick={{ fontSize: 11, fill: muted }} />
                <YAxis width={64} tickFormatter={axisMoney} tick={{ fontSize: 11, fill: muted }} />
                <Tooltip contentStyle={tipStyle} itemStyle={{ color: ink }} labelStyle={{ color: muted }} labelFormatter={(ms) => formatAxisDate(Number(ms))} formatter={(value) => euro.format(Number(value))} />
                <Line type="monotone" dataKey="historical" stroke={color} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} name="Wealth" />
                <Line type="monotone" dataKey="forecast" stroke={forecastColor} strokeWidth={2} strokeDasharray="6 3" dot={false} activeDot={{ r: 3 }} name="Forecast (invested)" />
                <Line type="monotone" dataKey="noInvest" stroke={muted} strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={{ r: 3 }} name="Forecast (0% invest)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="wealth-split-objectives">
          <h3>Yearly Objectives</h3>
          <YearlyObjectivesTable objectives={objectives} onSaveTarget={onSaveTarget} />
        </div>
      </div>
    </div>
  );
}

function YearlyObjectivesTable({ objectives, onSaveTarget }: { objectives: YearlyObjective[]; onSaveTarget: (year: number, target: number) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  useEffect(() => {
    const next: Record<number, string> = {};
    for (const row of objectives) next[row.year] = row.target_net_worth == null ? "" : String(row.target_net_worth);
    setDrafts(next);
  }, [objectives]);
  return (
    <table className="objectives-table">
      <thead>
        <tr>
          <th>Year</th>
          <th>Target</th>
          <th>Forecast</th>
          <th>Actual</th>
        </tr>
      </thead>
      <tbody>
        {objectives.map((row) => (
          <tr key={row.year}>
            <td>{row.year}</td>
            <td>
              <input
                type="number"
                step="0.01"
                className="cell-input"
                value={drafts[row.year] ?? ""}
                onChange={(e) => setDrafts((prev) => ({ ...prev, [row.year]: e.target.value }))}
                onBlur={() => {
                  const raw = drafts[row.year];
                  if (raw === "" || raw == null) return;
                  void onSaveTarget(row.year, Number(raw));
                }}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  (e.target as HTMLInputElement).blur();
                }}
                placeholder="—"
              />
            </td>
            <td>{row.forecast_year_end == null ? "—" : euro.format(row.forecast_year_end)}</td>
            <td>{row.actual_net_worth == null ? "—" : euro.format(row.actual_net_worth)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function InvestmentLedger({ rows, onSaveReal }: { rows: InvestmentMonthRow[]; onSaveReal: (year: number, month: number, realValue: number | null) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  useEffect(() => {
    const next: Record<string, string> = {};
    for (const row of rows) next[`${row.year}-${row.month}`] = row.real_value == null ? "" : String(row.real_value);
    setDrafts(next);
  }, [rows]);
  const keyOf = (row: InvestmentMonthRow) => `${row.year}-${row.month}`;
  return (
    <div className="strategy-invest-wrap">
      <h3 className="strategy-invest-title">End-of-Month Investments</h3>
      <p className="muted strategy-invest-lead">Accum compounds invested amounts at S&amp;P. Enter real portfolio value to mark to market.</p>
      <div className="strategy-invest-scroll">
        <table className="strategy-invest-table">
          <thead>
            <tr>
              <th>Month</th>
              <th>Investment amount</th>
              <th>Investment %</th>
              <th>Accum value</th>
              <th>Real value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const key = keyOf(row);
              return (
                <tr key={key}>
                  <td>{row.label}</td>
                  <td>{euro.format(row.investment_amount)}</td>
                  <td>{whole.format(Math.round(row.investment_pct))}%</td>
                  <td>{euro.format(row.accum_value)}</td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      className="cell-input"
                      value={drafts[key] ?? ""}
                      onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                      onBlur={() => {
                        const raw = drafts[key];
                        const next = raw === "" || raw == null ? null : Number(raw);
                        if (next === row.real_value || (next == null && row.real_value == null)) return;
                        void onSaveReal(row.year, row.month, next);
                      }}
                      onKeyDown={(e) => {
                        if (e.key !== "Enter") return;
                        (e.target as HTMLInputElement).blur();
                      }}
                      placeholder="—"
                    />
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="muted">No months yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MonthTable({ rows, year, month, onSelect, onSaveOpeningWealth }: {
  rows: MonthNavRow[]; year: number; month: number;
  onSelect: (y: number, m: number) => void;
  onSaveOpeningWealth: (y: number, m: number, netWorth: number) => Promise<void>;
}) {
  const opening = rows.find((row) => row.is_opening) ?? rows[0];
  const [draft, setDraft] = useState(opening ? String(opening.net_worth) : "");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const activeRowRef = useRef<HTMLTableRowElement | null>(null);
  useEffect(() => {
    const row = rows.find((r) => r.is_opening) ?? rows[0];
    setDraft(row ? String(row.net_worth) : "");
  }, [rows]);
  useEffect(() => {
    const scroller = scrollRef.current;
    const last = rows[rows.length - 1];
    if (scroller && last && last.year === year && last.month === month) scroller.scrollTop = scroller.scrollHeight;
    else activeRowRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [year, month, rows]);
  return (
    <div className="panel month-table-panel">
      <h2>Month Over Month</h2>
      <p className="muted month-table-hint">Edit wealth on the first month to set a starting balance; later months = previous + wage − spend.</p>
      <div className="month-table-scroll" ref={scrollRef}>
        <table className="month-nav-table">
          <thead>
            <tr>
              <th>Month</th>
              <th>Wage</th>
              <th>Spend</th>
              <th>% Save</th>
              <th>Wealth</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const active = row.year === year && row.month === month;
              const saveTone = row.save_pct >= 40 ? "good" : row.save_pct >= 20 ? "mid" : "low";
              const isOpening = Boolean(row.is_opening);
              return (
                <tr
                  key={`${row.year}-${row.month}`}
                  ref={active ? activeRowRef : undefined}
                  className={`${active ? "is-active" : ""} save-${saveTone}`}
                  onClick={() => onSelect(row.year, row.month)}
                >
                  <td>{row.label}</td>
                  <td>{euro.format(row.income ?? 0)}</td>
                  <td className="amount-neg">{euro.format(row.real_spend)}</td>
                  <td>{whole.format(Math.round(row.save_pct))}%</td>
                  <td onClick={(e) => { if (isOpening) e.stopPropagation(); }}>
                    {isOpening ? (
                      <input
                        type="number"
                        step="0.01"
                        className="cell-input month-wealth-input"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={() => {
                          if (draft === "" || draft == null) return;
                          const next = Number(draft);
                          if (next === row.net_worth) return;
                          void onSaveOpeningWealth(row.year, row.month, next);
                        }}
                        onKeyDown={(e) => {
                          if (e.key !== "Enter") return;
                          (e.target as HTMLInputElement).blur();
                        }}
                      />
                    ) : euro.format(row.net_worth)}
                  </td>
                  <td>{row.net_worth_delta_pct == null ? "—" : `${whole.format(Math.round(row.net_worth_delta_pct))}%`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CompareBar({ label, actual, plan, color }: { label: string; actual: number; plan: number; color: string }) {
  return (
    <div className="compare-row">
      <div className="compare-head">
        <span>{label}</span>
        <span className="compare-legend">
          <span className="legend-actual">Actual {whole.format(Math.round(actual))}%</span>
          <span className="legend-plan">Plan {whole.format(Math.round(plan))}%</span>
        </span>
      </div>
      <div className="compare-track">
        <span className="compare-actual" style={{ width: `${Math.min(Math.max(actual, 0), 100)}%`, background: color }} />
        <span className="compare-plan-mark" style={{ left: `${Math.min(Math.max(plan, 0), 100)}%` }} />
      </div>
    </div>
  );
}

export function DashboardPage() {
  const [year, setYear] = useState<number | undefined>(undefined);
  const [month, setMonth] = useState<number | undefined>(undefined);
  const [data, setData] = useState<Dashboard | null>(null);
  const [spendPct, setSpendPct] = useState(50);
  const [savePct, setSavePct] = useState(25);
  const [investPct, setInvestPct] = useState(25);
  const [message, setMessage] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CategorySpend | null>(null);
  const [categoryExpenses, setCategoryExpenses] = useState<Transaction[]>([]);
  const [loadingExpenses, setLoadingExpenses] = useState(false);

  const planTotal = spendPct + savePct + investPct;

  async function load(selectedYear?: number, selectedMonth?: number) {
    const dash = await api.dashboard(selectedYear, selectedMonth);
    setData(dash);
    setYear(dash.month.year);
    setMonth(dash.month.month);
    setSpendPct(dash.strategy.spend_pct);
    setSavePct(dash.strategy.save_pct);
    setInvestPct(dash.strategy.invest_pct);
    setSelectedCategory(null);
    setCategoryExpenses([]);
  }

  useEffect(() => {
    load().catch((err: Error) => setMessage(err.message));
  }, []);

  async function changePeriod(nextYear: number, nextMonth: number) {
    setYear(nextYear);
    setMonth(nextMonth);
    await load(nextYear, nextMonth);
  }

  async function saveStrategy() {
    if (year == null || month == null) return;
    if (Math.round(spendPct + savePct + investPct) !== PCT_TOTAL_TARGET) {
      setMessage("Strategy must total 100%");
      return;
    }
    await api.updateStrategy(year, month, { spend_pct: spendPct, save_pct: savePct, invest_pct: investPct });
    setMessage("Strategy saved");
    await load(year, month);
  }

  async function saveInvestmentReal(rowYear: number, rowMonth: number, realValue: number | null) {
    await api.updateInvestmentReal(rowYear, rowMonth, realValue);
    setMessage("Real investment value saved");
    await load(year, month);
  }

  async function saveYearlyTarget(targetYear: number, target: number) {
    await api.updateYearlyObjective(targetYear, target);
    setMessage("Yearly objective saved");
    await load(year, month);
  }

  async function saveOpeningWealth(rowYear: number, rowMonth: number, netWorth: number) {
    await api.updateOpeningWealth(rowYear, rowMonth, netWorth);
    setMessage("Opening wealth saved");
    await load(year, month);
  }

  async function selectCategory(entry: CategorySpend) {
    if (!year || !month) return;
    if (selectedCategory?.category_name === entry.category_name) {
      setSelectedCategory(null);
      setCategoryExpenses([]);
      return;
    }
    setSelectedCategory(entry);
    setLoadingExpenses(true);
    const txs = await api.transactions({ year, month, category_id: entry.category_id, expenses_only: true }).finally(() => setLoadingExpenses(false));
    setCategoryExpenses(txs);
  }

  if (message && !data) return <p className="muted">{message}</p>;
  if (!data || year == null || month == null) return <p className="muted">Loading dashboard…</p>;
  const m = data.month;
  const investmentAccounts = data.accounts.filter((account) => account.account_type === ACCOUNT_TYPE_INVESTMENT);
  const hasInvestAccounts = investmentAccounts.length > 0;
  const deltaClass = m.net_worth_delta > 0 ? "save" : m.net_worth_delta < 0 ? "spend" : "";
  const a = data.projection_assumptions;
  const monthLabel = data.month_rows.find((r) => r.year === year && r.month === month)?.label || `${year}-${month}`;

  return (
    <div className="dash-stack">
      <MonthTable
        rows={data.month_rows}
        year={year}
        month={month}
        onSelect={(y, mo) => changePeriod(y, mo).catch((err: Error) => setMessage(err.message))}
        onSaveOpeningWealth={(y, mo, nw) => saveOpeningWealth(y, mo, nw).catch((err: Error) => setMessage(err.message))}
      />
      {message && <p className="muted">{message}</p>}

      <div className="grid stats">
        <div className="panel"><div className="stat-label">Wage</div><div className="stat-value save">{euro.format(m.income)}</div></div>
        <div className="panel"><div className="stat-label">Spend</div><div className="stat-value spend">{euro.format(m.real_spend)}</div></div>
        <div className="panel">
          <div className="stat-label">Saved</div>
          <div className="stat-value save">{euro.format(m.save_amount)}</div>
          <div className="stat-sub">{whole.format(Math.round(m.save_pct))}% of wage</div>
        </div>
        <div className="panel">
          <div className="stat-label">Wealth</div>
          <div className="stat-value">{euro.format(m.net_worth)}</div>
          <div className={`stat-sub ${deltaClass}`}>{m.net_worth_delta_pct == null ? signedEuro(m.net_worth_delta) : `${signedEuro(m.net_worth_delta)} · ${whole.format(Math.round(m.net_worth_delta_pct))}%`}</div>
        </div>
      </div>

      <div className="grid two">
        <div className="panel strategy-panel">
          <h2>Month Strategy</h2>
          <p className="muted strategy-lead">Plan for this month. Projection uses spend / save / invest below.</p>
          <div className="strategy-targets">
            <label className="strategy-field is-spend">
              <span className="strategy-field-label">Spend %</span>
              <input type="number" min={0} max={100} value={spendPct} onChange={(e) => setSpendPct(Number(e.target.value))} />
            </label>
            <label className="strategy-field is-save">
              <span className="strategy-field-label">Save %</span>
              <input type="number" min={0} max={100} value={savePct} onChange={(e) => setSavePct(Number(e.target.value))} />
            </label>
            <label className="strategy-field is-invest">
              <span className="strategy-field-label">Invest %</span>
              <input type="number" min={0} max={100} value={investPct} onChange={(e) => setInvestPct(Number(e.target.value))} />
            </label>
          </div>
          <div className="strategy-footer">
            <p className={`strategy-total${Math.round(planTotal) === PCT_TOTAL_TARGET ? "" : " is-warn"}`}>
              {Math.round(planTotal) === PCT_TOTAL_TARGET ? "Plan totals 100%" : `Plan totals ${whole.format(Math.round(planTotal))}%`}
            </p>
            <button type="button" disabled={Math.round(planTotal) !== PCT_TOTAL_TARGET} onClick={() => saveStrategy().catch((e: Error) => setMessage(e.message))}>Save</button>
          </div>
          <div className="strategy-compare">
            <CompareBar label="Spend" actual={m.actual_spend_pct} plan={spendPct} color="var(--spend)" />
            <CompareBar label="Save" actual={m.actual_save_pct} plan={savePct} color="var(--save)" />
            <CompareBar label="Invest" actual={m.actual_invest_pct} plan={investPct} color="var(--invest)" />
          </div>
          <InvestmentLedger rows={data.investment_month_rows || []} onSaveReal={(y, mo, v) => saveInvestmentReal(y, mo, v).catch((err: Error) => setMessage(err.message))} />
        </div>

        <div className="panel cat-panel">
          <h2>Spend By Category · {monthLabel}</h2>
          <p className="muted cat-hint">
            You vs typical for {data.benchmark_location || "your region"}
            {data.benchmark_source === "llm" ? " (AI estimate)" : " (Eurostat-based)"}
            . Click a row to open expenses.
          </p>
          <div className="cat-bars">
            {data.spend_by_category.map((entry) => {
              const active = selectedCategory?.category_name === entry.category_name;
              const maxAmt = Math.max(entry.amount, entry.benchmark_amount || 0, 1);
              const youWidth = Math.min((entry.amount / maxAmt) * 100, 100);
              const typicalWidth = entry.benchmark_amount != null ? Math.min((entry.benchmark_amount / maxAmt) * 100, 100) : 0;
              return (
                <button
                  key={entry.category_name}
                  type="button"
                  className={`cat-bar-row${active ? " is-active" : ""}`}
                  onClick={() => selectCategory(entry).catch((err: Error) => setMessage(err.message))}
                >
                  <div className="cat-bar-meta">
                    <span className="cat-swatch" style={{ background: entry.color }} />
                    <span className="cat-name">{entry.category_name}</span>
                    <span className="cat-compare">
                      <span className="cat-amt">You {euro.format(entry.amount)}</span>
                      {entry.benchmark_amount != null && (
                        <span className="cat-typical">Typical {euro.format(entry.benchmark_amount)}</span>
                      )}
                    </span>
                  </div>
                  <div className="cat-bar-track cat-bar-track-dual">
                    <span className="cat-bar-you" style={{ width: `${youWidth}%`, background: entry.color }} />
                    {entry.benchmark_amount != null && (
                      <span className="cat-bar-typical" style={{ width: `${typicalWidth}%` }} />
                    )}
                  </div>
                </button>
              );
            })}
            {data.spend_by_category.length === 0 && <p className="muted">No spend this month.</p>}
          </div>
        </div>
      </div>

      {year != null && month != null && (
        <AdvisorChat year={year} month={month} onMutated={() => { void load(year, month); }} />
      )}

      <div className="panel invest-panel">
        <div className="invest-panel-head">
          <h2>Investments</h2>
          {hasInvestAccounts && <div className="stat-value invest">{euro.format(data.invested_total)}</div>}
        </div>
        {!hasInvestAccounts && (
          <p className="muted">No investment accounts yet. Add S&amp;P 500 (or another broker) on <Link to="/accounts">Accounts File Connection</Link> and import balance history.</p>
        )}
        {hasInvestAccounts && (
          <table className="table">
            <thead><tr><th>Account</th><th>Institution</th><th>Balance</th></tr></thead>
            <tbody>
              {investmentAccounts.map((account) => (
                <tr key={account.id}>
                  <td>{account.name}</td>
                  <td>{account.institution || "—"}</td>
                  <td>{euro.format(account.latest_balance ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <CombinedWealthPanel
        title="Accumulated Wealth & 1Y Forecast"
        historical={data.wealth_series}
        forecast={data.wealth_projection}
        forecastNoInvest={data.wealth_projection_no_invest}
        color={themeColor("--accent-2")}
        forecastColor={themeColor("--accent")}
        note={`Forecast: spend ${whole.format(Math.round(a.spend_pct))}% · save ${whole.format(Math.round(a.save_pct))}% · invest ${whole.format(Math.round(a.invest_pct))}% · S&P ${a.sp500_annual_return_pct}%/yr`}
        objectives={data.yearly_objectives || []}
        onSaveTarget={(y, t) => saveYearlyTarget(y, t).catch((err: Error) => setMessage(err.message))}
      />

      <div className="panel cat-detail-panel">
        <div className="cat-expenses-head">
          <h2>{selectedCategory ? selectedCategory.category_name : "Category Expenses"}</h2>
          {selectedCategory && <button type="button" className="secondary" onClick={() => { setSelectedCategory(null); setCategoryExpenses([]); }}>Clear</button>}
        </div>
        {!selectedCategory && <p className="muted">Select a category to list expenses for {monthLabel}.</p>}
        {selectedCategory && loadingExpenses && <p className="muted">Loading…</p>}
        {selectedCategory && !loadingExpenses && categoryExpenses.length === 0 && <p className="muted">No expenses in this category.</p>}
        {selectedCategory && !loadingExpenses && categoryExpenses.length > 0 && (
          <table className="table">
            <thead><tr><th>Date</th><th>Description</th><th>Amount</th></tr></thead>
            <tbody>
              {categoryExpenses.flatMap((tx) => {
                const portions = (tx.splits || []).filter((s) => s.category_id === selectedCategory.category_id || (s.category_id == null && tx.category_id === selectedCategory.category_id));
                if (portions.length > 0) {
                  return portions.map((split) => (
                    <tr key={`${tx.id}-${split.id}`}>
                      <td>{tx.booked_at}</td>
                      <td>{tx.merchant || tx.raw_description || "—"}{split.label ? ` · ${split.label}` : ""}</td>
                      <td className={amountClass(amountTone(split.amount, portionKind(split, tx)))}>{euro.format(Math.abs(split.amount))}</td>
                    </tr>
                  ));
                }
                return [(
                  <tr key={tx.id}>
                    <td>{tx.booked_at}</td>
                    <td>{tx.merchant || tx.raw_description || "—"}</td>
                    <td className={amountClass(amountTone(tx.amount, tx.category_kind))}>{euro.format(Math.abs(tx.amount))}</td>
                  </tr>
                )];
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
