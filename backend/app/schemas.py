from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str
    role: str
    household_id: int
    model_config = {"from_attributes": True}


class HouseholdOut(BaseModel):
    id: int
    name: str
    invite_code: str
    location: str = ""
    model_config = {"from_attributes": True}


class ProfileUpdateIn(BaseModel):
    display_name: str | None = None
    location: str | None = None
    household_name: str | None = None


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str
    household_name: str = "Our household"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class JoinHouseholdIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str
    invite_code: str


class AccountCreate(BaseModel):
    name: str
    institution: str = ""
    currency: str = "EUR"
    account_type: str = "checking"
    source: str = "manual"
    iban: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    account_type: str | None = None
    iban: str | None = None
    is_active: bool | None = None


class AccountOut(BaseModel):
    id: int
    name: str
    institution: str
    currency: str
    account_type: str
    source: str
    is_active: bool
    iban: str | None = None
    latest_balance: float | None = None
    model_config = {"from_attributes": True}


class FlowNodeOut(BaseModel):
    id: str
    kind: str
    label: str
    amount: float
    account_id: int | None = None
    iban: str | None = None


class FlowEdgeOut(BaseModel):
    source: str
    target: str
    amount: float
    kind: str


class AccountFlowOut(BaseModel):
    year: int
    month: int
    nodes: list[FlowNodeOut]
    edges: list[FlowEdgeOut]


class BalanceIn(BaseModel):
    amount: float
    snapshot_date: date | None = None


class BalanceOut(BaseModel):
    id: int
    account_id: int
    snapshot_date: date
    amount: float
    model_config = {"from_attributes": True}


class CategoryOut(BaseModel):
    id: int
    name: str
    kind: str
    color: str
    model_config = {"from_attributes": True}


class TransactionSplitOut(BaseModel):
    id: int
    amount: float
    label: str
    category_id: int | None
    category_name: str | None = None
    category_kind: str | None = None
    sort_order: int = 0
    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: int
    account_id: int
    category_id: int | None
    booked_at: date
    amount: float
    currency: str
    raw_description: str
    merchant: str
    counterparty: str = ""
    counterparty_iban: str = ""
    location: str = ""
    mcc: str | None = None
    value_date: date | None = None
    balance_after: float | None = None
    source: str
    category_name: str | None = None
    category_kind: str | None = None
    splits: list[TransactionSplitOut] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class TransactionAssignIn(BaseModel):
    category_id: int
    create_rule: bool = True
    rule_pattern: str | None = None


class TransactionSplitPortionIn(BaseModel):
    amount: float
    label: str = ""
    category_id: int | None = None


class TransactionSplitIn(BaseModel):
    portions: list[TransactionSplitPortionIn] = Field(min_length=2)


class EmployersIn(BaseModel):
    companies: list[str]


class EmployersOut(BaseModel):
    created: int
    companies: list[str]


class MonthlyStrategyOut(BaseModel):
    year: int
    month: int
    save_pct: float
    spend_pct: float
    invest_pct: float
    model_config = {"from_attributes": True}


class MonthlyStrategyIn(BaseModel):
    save_pct: float
    spend_pct: float
    invest_pct: float


class InvestmentRealIn(BaseModel):
    real_value: float | None = None


class InvestmentRealOut(BaseModel):
    year: int
    month: int
    real_value: float | None = None
    model_config = {"from_attributes": True}


class InvestmentMonthRowOut(BaseModel):
    year: int
    month: int
    label: str
    investment_amount: float
    investment_pct: float
    accum_value: float
    real_value: float | None = None
    cum_invest: float = 0.0


class YearlyObjectiveIn(BaseModel):
    target_net_worth: float


class YearlyObjectiveOut(BaseModel):
    year: int
    target_net_worth: float | None = None
    forecast_year_end: float | None = None
    actual_net_worth: float | None = None


class MonthNavRowOut(BaseModel):
    year: int
    month: int
    label: str
    income: float
    real_spend: float
    save_pct: float
    net_worth: float
    net_worth_delta_pct: float | None
    is_opening: bool = False


class OpeningWealthIn(BaseModel):
    net_worth: float


class OpeningWealthOut(BaseModel):
    year: int
    month: int
    net_worth: float
    model_config = {"from_attributes": True}


class InstitutionOut(BaseModel):
    id: str
    name: str
    country: str
    logo: str | None = None


class BankConnectionOut(BaseModel):
    id: int
    provider: str
    institution_id: str
    institution_name: str
    status: str
    consent_expires_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime
    is_mock: bool = False
    model_config = {"from_attributes": True}


class AuthStartOut(BaseModel):
    authorization_url: str
    connection_id: int


class MonthlySummaryOut(BaseModel):
    year: int
    month: int
    income: float
    real_spend: float
    save_amount: float
    save_pct: float
    net_worth: float
    net_worth_delta: float
    net_worth_delta_pct: float | None
    recommended_spend: float
    recommended_save: float
    recommended_invest: float
    actual_spend_pct: float
    actual_save_pct: float
    actual_invest_pct: float


class CategorySpendOut(BaseModel):
    category_id: int | None
    category_name: str
    amount: float
    pct: float
    color: str
    benchmark_amount: float | None = None
    benchmark_pct: float | None = None


class DashboardOut(BaseModel):
    net_worth: float
    month: MonthlySummaryOut
    spend_by_category: list[CategorySpendOut]
    accounts: list[AccountOut]
    invested_total: float = 0.0
    strategy: MonthlyStrategyOut
    month_rows: list[MonthNavRowOut]
    investment_month_rows: list[InvestmentMonthRowOut] = Field(default_factory=list)
    yearly_objectives: list[YearlyObjectiveOut] = Field(default_factory=list)
    wealth_series: list[dict]
    wealth_projection: list[dict]
    wealth_projection_no_invest: list[dict]
    projection_assumptions: dict
    benchmark_location: str = ""
    benchmark_source: str = ""


class ImportResult(BaseModel):
    imported: int
    skipped: int
    replaced: int = 0
    categorized: int = 0
    account_id: int
    overwrite: bool = False
    account_type: str | None = None
    format_detected: str | None = None
    contributions: float | None = None
    purchases: float | None = None
    dividends: float | None = None
    management_fees: float | None = None
    securities: int | None = None
    currency: str | None = None
    unknown_types: list[str] = []
    transactions: int | None = None


class RevolutImportPreview(BaseModel):
    account_type: str = "investment"
    format_detected: str
    transactions: int
    contributions: float
    purchases: float
    dividends: float
    management_fees: float
    securities: int
    currency: str
    unknown_types: list[str] = []


class ClassifyResult(BaseModel):
    categorized: int
    account_id: int | None = None
    remaining: int = 0


class AdvisorChatMessage(BaseModel):
    role: str
    content: str


class AdvisorChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[AdvisorChatMessage] = Field(default_factory=list)
    year: int
    month: int = Field(ge=1, le=12)


class AdvisorActionResult(BaseModel):
    type: str
    count: int = 0
    category_name: str | None = None
    transaction_ids: list[int] = Field(default_factory=list)
    detail: str = ""


class AdvisorChatOut(BaseModel):
    reply: str
    action_results: list[AdvisorActionResult] = Field(default_factory=list)
    mutated: bool = False
