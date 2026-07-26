export type User = { id: number; email: string; display_name: string; role: string; household_id: number };
export type Household = { id: number; name: string; invite_code: string };
export type Account = { id: number; name: string; institution: string; currency: string; account_type: string; source: string; is_active: boolean; latest_balance: number | null };
export type Category = { id: number; name: string; kind: string; color: string };
export type Transaction = { id: number; account_id: number; category_id: number | null; booked_at: string; amount: number; currency: string; raw_description: string; merchant: string; source: string; category_name: string | null };
export type Institution = { id: string; name: string; country: string; logo: string | null };
export type BankConnection = { id: number; provider: string; institution_id: string; institution_name: string; status: string; consent_expires_at: string | null; last_synced_at: string | null };
export type Allocation = { spend_pct: number; save_pct: number; invest_pct: number };
export type MonthlySummary = {
  year: number; month: number; income: number; real_spend: number; save_amount: number; save_pct: number;
  net_worth: number; net_worth_delta_pct: number | null; recommended_spend: number; recommended_save: number;
  recommended_invest: number; actual_spend_pct: number; actual_save_pct: number; actual_invest_pct: number;
};
export type CategorySpend = { category_id: number | null; category_name: string; amount: number; pct: number; color: string };
export type SeriesPoint = { label: string; value: number };
export type Dashboard = {
  net_worth: number; month: MonthlySummary; spend_by_category: CategorySpend[]; accounts: Account[];
  allocation: Allocation; net_worth_series: SeriesPoint[]; wealth_no_invest_series: SeriesPoint[];
  wealth_with_invest_series: SeriesPoint[]; connections: BankConnection[];
};

const TOKEN_KEY = "tyf_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  register: (body: object) => request<{ access_token: string }>("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body: object) => request<{ access_token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  join: (body: object) => request<{ access_token: string }>("/api/auth/join", { method: "POST", body: JSON.stringify(body) }),
  me: () => request<User>("/api/auth/me"),
  household: () => request<Household>("/api/auth/household"),
  dashboard: (year?: number, month?: number) => {
    const q = new URLSearchParams();
    if (year != null) q.set("year", String(year));
    if (month != null) q.set("month", String(month));
    const suffix = q.toString() ? `?${q}` : "";
    return request<Dashboard>(`/api/dashboard${suffix}`);
  },
  updateAllocation: (body: Allocation) => request<Allocation>("/api/dashboard/allocation", { method: "PUT", body: JSON.stringify(body) }),
  accounts: () => request<Account[]>("/api/accounts"),
  createAccount: (body: object) => request<Account>("/api/accounts", { method: "POST", body: JSON.stringify(body) }),
  addBalance: (accountId: number, amount: number, snapshot_date?: string) =>
    request(`/api/accounts/${accountId}/balances`, { method: "POST", body: JSON.stringify({ amount, snapshot_date }) }),
  categories: () => request<Category[]>("/api/categories"),
  transactions: (uncategorized = false) => request<Transaction[]>(`/api/transactions?uncategorized=${uncategorized}`),
  assignCategory: (id: number, body: object) => request<Transaction>(`/api/transactions/${id}/assign`, { method: "POST", body: JSON.stringify(body) }),
  importCsv: (accountId: number, file: File) => {
    const form = new FormData();
    form.append("account_id", String(accountId));
    form.append("file", file);
    return request<{ imported: number; skipped: number; account_id: number }>("/api/import/csv", { method: "POST", body: form });
  },
  institutions: () => request<Institution[]>("/api/banking/institutions"),
  connections: () => request<BankConnection[]>("/api/banking/connections"),
  connect: (institutionId: string) =>
    request<{ authorization_url: string; connection_id: number }>(`/api/banking/connect/${encodeURIComponent(institutionId)}`, { method: "POST" }),
  sync: (connectionId: number) => request<{ imported: number; status: string }>(`/api/banking/connections/${connectionId}/sync`, { method: "POST" }),
  reconnect: (connectionId: number) =>
    request<{ authorization_url: string; connection_id: number }>(`/api/banking/connections/${connectionId}/reconnect`, { method: "POST" }),
};
