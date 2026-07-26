import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, Pie, PieChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Dashboard } from "../api";
import { euro } from "../format";

export function DashboardPage() {
  const [year, setYear] = useState<number | null>(null);
  const [month, setMonth] = useState<number | null>(null);
  const [data, setData] = useState<Dashboard | null>(null);
  const [spendPct, setSpendPct] = useState(50);
  const [savePct, setSavePct] = useState(25);
  const [investPct, setInvestPct] = useState(25);
  const [message, setMessage] = useState("");

  async function load(selectedYear?: number | null, selectedMonth?: number | null) {
    const dash = await api.dashboard(selectedYear ?? undefined, selectedMonth ?? undefined);
    setData(dash);
    setYear(dash.month.year);
    setMonth(dash.month.month);
    setSpendPct(dash.allocation.spend_pct);
    setSavePct(dash.allocation.save_pct);
    setInvestPct(dash.allocation.invest_pct);
  }

  useEffect(() => {
    load(year, month).catch((err: Error) => setMessage(err.message));
  }, [year, month]);

  async function saveAllocation() {
    await api.updateAllocation({ spend_pct: spendPct, save_pct: savePct, invest_pct: investPct });
    setMessage("Allocation saved");
    await load(year, month);
  }

  if (!data) return <p className="muted">Loading dashboard…</p>;
  const m = data.month;

  return (
    <div>
      <section className="hero">
        <div className="pill">Household net worth</div>
        <div className="nw">{euro.format(data.net_worth)}</div>
        <p>
          Month view for {m.year}-{String(m.month).padStart(2, "0")}. Track spend, savings rate, and how your income should split across spend / save / invest.
        </p>
        <div className="row" style={{ maxWidth: 320 }}>
          <label>
            <div className="muted">Year</div>
            <input type="number" value={year ?? ""} onChange={(e) => setYear(Number(e.target.value))} />
          </label>
          <label>
            <div className="muted">Month</div>
            <input type="number" min={1} max={12} value={month ?? ""} onChange={(e) => setMonth(Number(e.target.value))} />
          </label>
        </div>
        {message && <p className="muted" style={{ marginTop: "0.75rem" }}>{message}</p>}
      </section>

      <div className="grid stats" style={{ marginBottom: "1rem" }}>
        <div className="panel">
          <div className="stat-label">Income (salary & inflows)</div>
          <div className="stat-value save">{euro.format(m.income)}</div>
        </div>
        <div className="panel">
          <div className="stat-label">Spend (negative txs)</div>
          <div className="stat-value spend">{euro.format(m.real_spend)}</div>
        </div>
        <div className="panel">
          <div className="stat-label">Saved this month</div>
          <div className="stat-value save">{euro.format(m.save_amount)} · {m.save_pct}%</div>
        </div>
        <div className="panel">
          <div className="stat-label">Net worth Δ</div>
          <div className="stat-value">{m.net_worth_delta_pct == null ? "—" : `${m.net_worth_delta_pct}%`}</div>
        </div>
      </div>

      <div className="grid two" style={{ marginBottom: "1rem" }}>
        <div className="panel">
          <h2>Income split — recommended vs actual</h2>
          <div className="split">
            <div className="split-row"><span>Spend</span><div className="bar"><span style={{ width: `${m.actual_spend_pct}%`, background: "var(--spend)" }} /></div><strong>{m.actual_spend_pct}% / {data.allocation.spend_pct}%</strong></div>
            <div className="split-row"><span>Save</span><div className="bar"><span style={{ width: `${Math.max(m.actual_save_pct, 0)}%`, background: "var(--save)" }} /></div><strong>{m.actual_save_pct}% / {data.allocation.save_pct}%</strong></div>
            <div className="split-row"><span>Invest</span><div className="bar"><span style={{ width: `${m.actual_invest_pct}%`, background: "var(--invest)" }} /></div><strong>{m.actual_invest_pct}% / {data.allocation.invest_pct}%</strong></div>
          </div>
          <p className="muted" style={{ marginTop: "0.85rem" }}>
            Targets this month: spend {euro.format(m.recommended_spend)}, save {euro.format(m.recommended_save)}, invest {euro.format(m.recommended_invest)}.
          </p>
          <div className="row" style={{ marginTop: "1rem" }}>
            <label><div className="muted">Spend %</div><input type="number" value={spendPct} onChange={(e) => setSpendPct(Number(e.target.value))} /></label>
            <label><div className="muted">Save %</div><input type="number" value={savePct} onChange={(e) => setSavePct(Number(e.target.value))} /></label>
            <label><div className="muted">Invest %</div><input type="number" value={investPct} onChange={(e) => setInvestPct(Number(e.target.value))} /></label>
            <button type="button" onClick={() => saveAllocation().catch((e: Error) => setMessage(e.message))}>Save plan</button>
          </div>
        </div>
        <div className="panel">
          <h2>Spend by category</h2>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={data.spend_by_category} dataKey="amount" nameKey="category_name" innerRadius={55} outerRadius={95}>
                  {data.spend_by_category.map((entry) => <Cell key={entry.category_name} fill={entry.color} />)}
                </Pie>
                <Tooltip formatter={(value) => euro.format(Number(value))} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid charts" style={{ marginBottom: "1rem" }}>
        <div className="panel">
          <h2>Accum wealth without investments</h2>
          <div style={{ width: "100%", height: 240 }}>
            <ResponsiveContainer>
              <LineChart data={data.wealth_no_invest_series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(28,36,32,0.1)" />
                <XAxis dataKey="label" hide />
                <YAxis width={60} />
                <Tooltip formatter={(value) => euro.format(Number(value))} />
                <Line type="monotone" dataKey="value" stroke="#c45c26" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <h2>Accum wealth with investments</h2>
          <div style={{ width: "100%", height: 240 }}>
            <ResponsiveContainer>
              <LineChart data={data.wealth_with_invest_series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(28,36,32,0.1)" />
                <XAxis dataKey="label" hide />
                <YAxis width={60} />
                <Tooltip formatter={(value) => euro.format(Number(value))} />
                <Line type="monotone" dataKey="value" stroke="#1f6f5b" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Account balances</h2>
        <table className="table">
          <thead><tr><th>Account</th><th>Institution</th><th>Type</th><th>Balance</th></tr></thead>
          <tbody>
            {data.accounts.map((account) => (
              <tr key={account.id}>
                <td>{account.name}</td>
                <td>{account.institution || "—"}</td>
                <td>{account.account_type}</td>
                <td>{euro.format(account.latest_balance ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
