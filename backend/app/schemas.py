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


class AccountOut(BaseModel):
    id: int
    name: str
    institution: str
    currency: str
    account_type: str
    source: str
    is_active: bool
    latest_balance: float | None = None
    model_config = {"from_attributes": True}


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


class TransactionOut(BaseModel):
    id: int
    account_id: int
    category_id: int | None
    booked_at: date
    amount: float
    currency: str
    raw_description: str
    merchant: str
    source: str
    category_name: str | None = None
    model_config = {"from_attributes": True}


class TransactionAssignIn(BaseModel):
    category_id: int
    create_rule: bool = True
    rule_pattern: str | None = None


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


class MonthNavRowOut(BaseModel):
    year: int
    month: int
    label: str
    income: float
    real_spend: float
    save_pct: float
    net_worth: float
    net_worth_delta_pct: float | None


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


class ClassifyResult(BaseModel):
    categorized: int
    account_id: int | None = None


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
