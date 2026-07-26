import { useEffect, useState, type FormEvent } from "react";
import { api, type Account, type Category, type Transaction } from "../api";

const euro = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });

export function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [onlyUncategorized, setOnlyUncategorized] = useState(false);
  const [message, setMessage] = useState("");
  const [accountId, setAccountId] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);

  async function load() {
    const [txs, cats, accs] = await Promise.all([api.transactions(onlyUncategorized), api.categories(), api.accounts()]);
    setTransactions(txs);
    setCategories(cats);
    setAccounts(accs);
    if (!accountId && accs[0]) setAccountId(accs[0].id);
  }

  useEffect(() => {
    load().catch((err: Error) => setMessage(err.message));
  }, [onlyUncategorized]);

  async function assign(txId: number, categoryId: number) {
    await api.assignCategory(txId, { category_id: categoryId, create_rule: true });
    await load();
  }

  async function onImport(event: FormEvent) {
    event.preventDefault();
    if (!file || !accountId) return;
    const result = await api.importCsv(Number(accountId), file);
    setMessage(`Imported ${result.imported}, skipped ${result.skipped}`);
    setFile(null);
    await load();
  }

  return (
    <div>
      <section className="hero">
        <h1>Transactions</h1>
        <p>Classify spending, import bank CSVs, and grow rules from one-click assigns.</p>
      </section>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2>Import CSV</h2>
        <p className="muted">Columns supported: date/Fecha, amount/Importe, description/Concepto, merchant, external_id.</p>
        <form className="row" onSubmit={(e) => onImport(e).catch((err: Error) => setMessage(err.message))}>
          <label>
            <div className="muted">Account</div>
            <select value={accountId} onChange={(e) => setAccountId(Number(e.target.value))} required>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label>
            <div className="muted">CSV file</div>
            <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          </label>
          <button type="submit">Import</button>
        </form>
        {message && <p className="muted">{message}</p>}
      </div>

      <div className="panel">
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <h2 style={{ flex: 2 }}>Ledger</h2>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input type="checkbox" checked={onlyUncategorized} onChange={(e) => setOnlyUncategorized(e.target.checked)} />
            Uncategorized inbox
          </label>
        </div>
        <table className="table">
          <thead>
            <tr><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th>Assign</th></tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{tx.booked_at}</td>
                <td>{tx.merchant || tx.raw_description || "—"}</td>
                <td className={tx.amount >= 0 ? "amount-pos" : "amount-neg"}>{euro.format(tx.amount)}</td>
                <td>{tx.category_name || <span className="pill warn">Uncategorized</span>}</td>
                <td>
                  <select defaultValue="" onChange={(e) => { const value = Number(e.target.value); if (value) assign(tx.id, value).catch((err: Error) => setMessage(err.message)); }}>
                    <option value="" disabled>Choose…</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
