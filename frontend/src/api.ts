export type User = { id: number; email: string; display_name: string; role: string; household_id: number };
export type Household = { id: number; name: string; invite_code: string; location?: string };
export type Account = { id: number; name: string; institution: string; currency: string; account_type: string; source: string; is_active: boolean; iban: string | null; latest_balance: number | null };
export type FlowNode = {
  id: string;
  kind: "income" | "account" | "expenses" | string;
  label: string;
  amount: number;
  account_id?: number | null;
  iban?: string | null;
};
export type FlowEdge = { source: string; target: string; amount: number; kind: "income" | "spend" | "transfer" | string };
export type AccountFlow = { year: number; month: number; nodes: FlowNode[]; edges: FlowEdge[] };
export type Category = { id: number; name: string; kind: string; color: string };
export type TransactionSplit = { id: number; amount: number; label: string; category_id: number | null; category_name: string | null; category_kind: string | null; sort_order: number };
export type Transaction = {
  id: number; account_id: number; category_id: number | null; booked_at: string; amount: number; currency: string;
  raw_description: string; merchant: string; counterparty?: string; counterparty_iban?: string; location?: string;
  mcc?: string | null; value_date?: string | null; balance_after?: number | null;
  source: string; category_name: string | null; category_kind: string | null; splits?: TransactionSplit[];
};
export type Institution = { id: string; name: string; country: string; logo: string | null };
export type BankConnection = { id: number; provider: string; institution_id: string; institution_name: string; status: string; consent_expires_at: string | null; last_synced_at: string | null; created_at: string; is_mock: boolean };
export type MonthlyStrategy = { year: number; month: number; save_pct: number; spend_pct: number; invest_pct: number };
export type InvestmentMonthRow = {
  year: number; month: number; label: string;
  investment_amount: number; investment_pct: number; accum_value: number;
  real_value: number | null; cum_invest: number;
};
export type YearlyObjective = {
  year: number; target_net_worth: number | null;
  forecast_year_end: number | null; actual_net_worth: number | null;
};
export type MonthNavRow = {
  year: number; month: number; label: string; income: number; real_spend: number;
  save_pct: number; net_worth: number; net_worth_delta_pct: number | null;
  is_opening?: boolean;
};
export type MonthlySummary = {
  year: number; month: number; income: number; real_spend: number; save_amount: number; save_pct: number;
  net_worth: number; net_worth_delta: number; net_worth_delta_pct: number | null; recommended_spend: number; recommended_save: number;
  recommended_invest: number; actual_spend_pct: number; actual_save_pct: number; actual_invest_pct: number;
};
export type CategorySpend = {
  category_id: number | null; category_name: string; amount: number; pct: number; color: string;
  benchmark_amount?: number | null; benchmark_pct?: number | null;
};
export type SeriesPoint = { label: string; value: number; kind?: string };
export type ProjectionAssumptions = {
  avg_monthly_income: number; avg_monthly_spend: number;
  spend_pct: number; save_pct: number; invest_pct: number;
  sp500_annual_return_pct: number; years: number;
};
export type Dashboard = {
  net_worth: number; month: MonthlySummary; spend_by_category: CategorySpend[]; accounts: Account[];
  invested_total: number;
  strategy: MonthlyStrategy; month_rows: MonthNavRow[];
  investment_month_rows: InvestmentMonthRow[];
  yearly_objectives: YearlyObjective[];
  wealth_series: SeriesPoint[];
  wealth_projection: SeriesPoint[]; wealth_projection_no_invest: SeriesPoint[]; projection_assumptions: ProjectionAssumptions;
  benchmark_location?: string; benchmark_source?: string;
};

export type ImportResult = {
  imported: number;
  skipped: number;
  replaced: number;
  categorized: number;
  account_id: number;
  overwrite: boolean;
  account_type?: string | null;
  format_detected?: string | null;
  contributions?: number | null;
  purchases?: number | null;
  dividends?: number | null;
  management_fees?: number | null;
  securities?: number | null;
  currency?: string | null;
  unknown_types?: string[];
  transactions?: number | null;
};
export type RevolutImportPreview = {
  account_type: string;
  format_detected: string;
  transactions: number;
  contributions: number;
  purchases: number;
  dividends: number;
  management_fees: number;
  securities: number;
  currency: string;
  unknown_types: string[];
};
export type ClassifyResult = { categorized: number; account_id: number | null; remaining: number };
export type AdvisorChatMessage = { role: "user" | "assistant"; content: string };
export type AdvisorActionResult = {
  type: string;
  count: number;
  category_name: string | null;
  transaction_ids: number[];
  detail: string;
};
export type AdvisorChatResult = { reply: string; action_results: AdvisorActionResult[]; mutated: boolean };

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
    let message = detail || response.statusText;
    try {
      const parsed = JSON.parse(detail) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
      else if (parsed.detail != null) message = JSON.stringify(parsed.detail);
    } catch {
      // keep raw text
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function uploadCsv(path: string, accountId: number, file: File, overwrite = false, signal?: AbortSignal) {
  const form = new FormData();
  form.append("account_id", String(accountId));
  form.append("overwrite", String(overwrite));
  form.append("file", file);
  return request<ImportResult>(path, { method: "POST", body: form, signal });
}

export const api = {
  register: (body: object) => request<{ access_token: string }>("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body: object) => request<{ access_token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  join: (body: object) => request<{ access_token: string }>("/api/auth/join", { method: "POST", body: JSON.stringify(body) }),
  me: () => request<User>("/api/auth/me"),
  household: () => request<Household>("/api/auth/household"),
  updateProfile: (body: { display_name?: string; household_name?: string; location?: string }) =>
    request<Household>("/api/auth/profile", { method: "PUT", body: JSON.stringify(body) }),
  dashboard: (year?: number, month?: number) => {
    const q = new URLSearchParams();
    if (year != null) q.set("year", String(year));
    if (month != null) q.set("month", String(month));
    const suffix = q.toString() ? `?${q}` : "";
    return request<Dashboard>(`/api/dashboard${suffix}`);
  },
  updateStrategy: (year: number, month: number, body: { spend_pct: number; save_pct: number; invest_pct: number }) =>
    request<MonthlyStrategy>(`/api/dashboard/strategy?year=${year}&month=${month}`, { method: "PUT", body: JSON.stringify(body) }),
  updateInvestmentReal: (year: number, month: number, real_value: number | null) =>
    request<{ year: number; month: number; real_value: number | null }>(`/api/dashboard/investment-real?year=${year}&month=${month}`, { method: "PUT", body: JSON.stringify({ real_value }) }),
  updateYearlyObjective: (year: number, target_net_worth: number) =>
    request<YearlyObjective>(`/api/dashboard/yearly-objective?year=${year}`, { method: "PUT", body: JSON.stringify({ target_net_worth }) }),
  updateOpeningWealth: (year: number, month: number, net_worth: number) =>
    request<{ year: number; month: number; net_worth: number }>(`/api/dashboard/opening-wealth?year=${year}&month=${month}`, { method: "PUT", body: JSON.stringify({ net_worth }) }),
  accounts: () => request<Account[]>("/api/accounts"),
  createAccount: (body: object) => request<Account>("/api/accounts", { method: "POST", body: JSON.stringify(body) }),
  updateAccount: (accountId: number, body: { name?: string; institution?: string; account_type?: string; iban?: string | null; is_active?: boolean }) =>
    request<Account>(`/api/accounts/${accountId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteAccount: (accountId: number) => request<Account>(`/api/accounts/${accountId}`, { method: "DELETE" }),
  accountFlow: (year: number, month: number) => request<AccountFlow>(`/api/accounts/flow?year=${year}&month=${month}`),
  addBalance: (accountId: number, amount: number, snapshot_date?: string) =>
    request(`/api/accounts/${accountId}/balances`, { method: "POST", body: JSON.stringify({ amount, snapshot_date }) }),
  categories: () => request<Category[]>("/api/categories"),
  registerEmployers: (companies: string[]) =>
    request<{ created: number; companies: string[] }>("/api/categories/employers", { method: "POST", body: JSON.stringify({ companies }) }),
  transactions: (opts?: { uncategorized?: boolean; year?: number; month?: number; category_id?: number | null; expenses_only?: boolean; q?: string }) => {
    const q = new URLSearchParams();
    if (opts?.uncategorized) q.set("uncategorized", "true");
    if (opts?.year != null) q.set("year", String(opts.year));
    if (opts?.month != null) q.set("month", String(opts.month));
    if (opts?.category_id === null) q.set("uncategorized_only", "true");
    else if (opts?.category_id != null) q.set("category_id", String(opts.category_id));
    if (opts?.expenses_only) q.set("expenses_only", "true");
    if (opts?.q) q.set("q", opts.q);
    const suffix = q.toString() ? `?${q}` : "";
    return request<Transaction[]>(`/api/transactions${suffix}`);
  },
  assignCategory: (id: number, body: object) => request<Transaction>(`/api/transactions/${id}/assign`, { method: "POST", body: JSON.stringify(body) }),
  splitTransaction: (id: number, portions: { amount: number; label: string; category_id: number | null }[]) =>
    request<Transaction>(`/api/transactions/${id}/split`, { method: "POST", body: JSON.stringify({ portions }) }),
  unsplitTransaction: (id: number) => request<Transaction>(`/api/transactions/${id}/split`, { method: "DELETE" }),
  importCsv: (accountId: number, file: File, overwrite = false, signal?: AbortSignal) =>
    uploadCsv("/api/import/csv", accountId, file, overwrite, signal),
  previewRevolutCsv: (file: File, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    return request<RevolutImportPreview>("/api/import/revolut-preview", { method: "POST", body: form, signal });
  },
  importRevolutCsv: (accountId: number, file: File, overwrite = false, signal?: AbortSignal) =>
    uploadCsv("/api/import/revolut-csv", accountId, file, overwrite, signal),
  classifyTransactions: (accountId?: number, signal?: AbortSignal) => {
    const suffix = accountId != null ? `?account_id=${accountId}` : "";
    return request<ClassifyResult>(`/api/transactions/classify${suffix}`, { method: "POST", signal });
  },
  advisorChat: (body: { message: string; history: AdvisorChatMessage[]; year: number; month: number }, signal?: AbortSignal) =>
    request<AdvisorChatResult>("/api/advisor/chat", { method: "POST", body: JSON.stringify(body), signal }),
  importInvestmentCsv: (accountId: number, file: File, overwrite = false) =>
    uploadCsv("/api/import/investment-csv", accountId, file, overwrite),
  institutions: () => request<Institution[]>("/api/banking/institutions"),
  connections: () => request<BankConnection[]>("/api/banking/connections"),
  connect: (institutionId: string, psuType: "personal" | "business" = "personal") =>
    request<{ authorization_url: string; connection_id: number }>(`/api/banking/connect/${encodeURIComponent(institutionId)}?psu_type=${psuType}`, { method: "POST" }),
  sync: (connectionId: number) => request<{ imported: number; status: string }>(`/api/banking/connections/${connectionId}/sync`, { method: "POST" }),
  reconnect: (connectionId: number, psuType: "personal" | "business" = "personal") =>
    request<{ authorization_url: string; connection_id: number }>(`/api/banking/connections/${connectionId}/reconnect?psu_type=${psuType}`, { method: "POST" }),
};
