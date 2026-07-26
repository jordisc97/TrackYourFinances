from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, Enum):
    owner = "owner"
    member = "member"


class AccountType(str, Enum):
    checking = "checking"
    savings = "savings"
    investment = "investment"
    other = "other"


class AccountSource(str, Enum):
    bank = "bank"
    manual = "manual"
    csv = "csv"


class ConnectionStatus(str, Enum):
    pending = "pending"
    active = "active"
    expired = "expired"
    error = "error"


class TransactionSource(str, Enum):
    bank = "bank"
    csv = "csv"
    manual = "manual"


class Household(Base):
    __tablename__ = "households"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    users: Mapped[list["User"]] = relationship(back_populates="household")
    accounts: Mapped[list["Account"]] = relationship(back_populates="household")
    categories: Mapped[list["Category"]] = relationship(back_populates="household")
    allocation_plan: Mapped["IncomeAllocationPlan | None"] = relationship(back_populates="household", uselist=False)
    bank_connections: Mapped[list["BankConnection"]] = relationship(back_populates="household")
    monthly_strategies: Mapped[list["MonthlyStrategy"]] = relationship(back_populates="household")
    spend_benchmark: Mapped["SpendBenchmark | None"] = relationship(back_populates="household", uselist=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.member.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    household: Mapped["Household"] = relationship(back_populates="users")


class BankConnection(Base):
    __tablename__ = "bank_connections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="enable_banking")
    institution_id: Mapped[str] = mapped_column(String(120), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=ConnectionStatus.pending.value)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    household: Mapped["Household"] = relationship(back_populates="bank_connections")
    accounts: Mapped[list["Account"]] = relationship(back_populates="bank_connection")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), nullable=False)
    bank_connection_id: Mapped[int | None] = mapped_column(ForeignKey("bank_connections.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    institution: Mapped[str] = mapped_column(String(120), default="")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    account_type: Mapped[str] = mapped_column(String(20), default=AccountType.checking.value)
    source: Mapped[str] = mapped_column(String(20), default=AccountSource.manual.value)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    household: Mapped["Household"] = relationship(back_populates="accounts")
    bank_connection: Mapped["BankConnection | None"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    balance_snapshots: Mapped[list["BalanceSnapshot"]] = relationship(back_populates="account")


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "snapshot_date", name="uq_balance_account_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    account: Mapped["Account"] = relationship(back_populates="balance_snapshots")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="expense")
    color: Mapped[str] = mapped_column(String(16), default="#6B7C5E")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    household: Mapped["Household"] = relationship(back_populates="categories")
    rules: Mapped[list["CategoryRule"]] = relationship(back_populates="category")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")


class CategoryRule(Base):
    __tablename__ = "category_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="contains")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped["Category"] = relationship(back_populates="rules")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("account_id", "external_id", name="uq_tx_account_external"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    booked_at: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    raw_description: Mapped[str] = mapped_column(String(512), default="")
    merchant: Mapped[str] = mapped_column(String(255), default="")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default=TransactionSource.manual.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    account: Mapped["Account"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship(back_populates="transactions")


class IncomeAllocationPlan(Base):
    __tablename__ = "income_allocation_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), unique=True, nullable=False)
    spend_pct: Mapped[float] = mapped_column(Float, nullable=False)
    save_pct: Mapped[float] = mapped_column(Float, nullable=False)
    invest_pct: Mapped[float] = mapped_column(Float, nullable=False)
    household: Mapped["Household"] = relationship(back_populates="allocation_plan")


class MonthlyStrategy(Base):
    __tablename__ = "monthly_strategies"
    __table_args__ = (UniqueConstraint("household_id", "year", "month", name="uq_strategy_household_month"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    crypto_pct: Mapped[float] = mapped_column(Float, default=10.0)
    stocks_pct: Mapped[float] = mapped_column(Float, default=10.0)
    etfs_pct: Mapped[float] = mapped_column(Float, default=10.0)
    save_pct: Mapped[float] = mapped_column(Float, default=40.0)
    spend_pct: Mapped[float] = mapped_column(Float, default=30.0)
    household: Mapped["Household"] = relationship(back_populates="monthly_strategies")


class SpendBenchmark(Base):
    __tablename__ = "spend_benchmarks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(120), default="")
    monthly_income: Mapped[float] = mapped_column(Float, default=0.0)
    benchmarks_json: Mapped[str] = mapped_column(String(4000), default="{}")
    source: Mapped[str] = mapped_column(String(40), default="fallback")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    household: Mapped["Household"] = relationship(back_populates="spend_benchmark")
