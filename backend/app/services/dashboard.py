from calendar import monthrange
from collections import defaultdict
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import Account, AccountType, BalanceSnapshot, Household, IncomeAllocationPlan, MonthlyStrategy, Transaction
from app.schemas import (
    AccountOut,
    AllocationPlanOut,
    CategorySpendOut,
    DashboardOut,
    MonthNavRowOut,
    MonthlyStrategyOut,
    MonthlySummaryOut,
)
from app.services.benchmarks import get_or_refresh_benchmarks

SP500_ANNUAL_RETURN = 0.10
DEFAULT_CRYPTO_PCT = 10.0
DEFAULT_STOCKS_PCT = 10.0
DEFAULT_ETFS_PCT = 10.0
DEFAULT_SAVE_PCT = 40.0
DEFAULT_SPEND_PCT = 30.0
NON_SPEND_KINDS = ("transfer", "investment")
CATALAN_MONTHS = ("gen", "feb", "març", "abr", "maig", "juny", "jul", "ago", "set", "oct", "nov", "des")


def category_kind(tx: Transaction) -> str | None:
    return tx.category.kind if tx.category is not None else None


def is_spend_outflow(tx: Transaction) -> bool:
    return tx.amount < 0 and category_kind(tx) not in NON_SPEND_KINDS


def is_invest_outflow(tx: Transaction) -> bool:
    return tx.amount < 0 and category_kind(tx) == "investment"


def month_flow_totals(txs: list[Transaction]) -> tuple[float, float, float, float]:
    income = round(sum(t.amount for t in txs if t.amount > 0), 2)
    real_spend = round(abs(sum(t.amount for t in txs if is_spend_outflow(t))), 2)
    invest_out = round(abs(sum(t.amount for t in txs if is_invest_outflow(t))), 2)
    save_amount = round(income - real_spend - invest_out, 2)
    return income, real_spend, invest_out, save_amount


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def month_label(year: int, month: int) -> str:
    return f"{CATALAN_MONTHS[month - 1]}-{str(year)[2:]}"


def account_balance_on(db: Session, account_id: int, as_of: date) -> float:
    earliest = db.query(func.min(Transaction.booked_at)).filter(Transaction.account_id == account_id).scalar()
    if earliest is not None and earliest <= as_of:
        opening = 0.0
        prior = (
            db.query(BalanceSnapshot)
            .filter(BalanceSnapshot.account_id == account_id, BalanceSnapshot.snapshot_date < earliest)
            .order_by(BalanceSnapshot.snapshot_date.desc())
            .first()
        )
        if prior is not None:
            opening = float(prior.amount)
        tx_sum = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(Transaction.account_id == account_id, Transaction.booked_at <= as_of).scalar()
        return opening + float(tx_sum)
    snap = (
        db.query(BalanceSnapshot)
        .filter(BalanceSnapshot.account_id == account_id, BalanceSnapshot.snapshot_date <= as_of)
        .order_by(BalanceSnapshot.snapshot_date.desc())
        .first()
    )
    return float(snap.amount) if snap else 0.0


def active_accounts(db: Session, household_id: int) -> list[Account]:
    return db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()


def household_account_ids(db: Session, household_id: int) -> list[int]:
    return [a.id for a in db.query(Account).filter(Account.household_id == household_id).all()]


def latest_balances(db: Session, household_id: int) -> dict[int, float]:
    today = date.today()
    return {account.id: account_balance_on(db, account.id, today) for account in active_accounts(db, household_id)}


def net_worth_on(db: Session, household_id: int, as_of: date, accounts: list[Account] | None = None) -> float:
    accounts = accounts if accounts is not None else active_accounts(db, household_id)
    return sum(account_balance_on(db, account.id, as_of) for account in accounts)


def latest_activity_month(db: Session, household_id: int) -> tuple[int, int] | None:
    account_ids = household_account_ids(db, household_id)
    if not account_ids:
        return None
    latest = db.query(Transaction.booked_at).filter(Transaction.account_id.in_(account_ids)).order_by(Transaction.booked_at.desc()).first()
    if latest is None:
        return None
    return latest[0].year, latest[0].month


def earliest_activity_month(db: Session, household_id: int) -> tuple[int, int] | None:
    account_ids = household_account_ids(db, household_id)
    if not account_ids:
        return None
    earliest = db.query(Transaction.booked_at).filter(Transaction.account_id.in_(account_ids)).order_by(Transaction.booked_at.asc()).first()
    if earliest is None:
        return None
    return earliest[0].year, earliest[0].month


def month_transactions(db: Session, household_id: int, year: int, month: int) -> list[Transaction]:
    account_ids = household_account_ids(db, household_id)
    if not account_ids:
        return []
    start, end = month_bounds(year, month)
    return (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(Transaction.account_id.in_(account_ids), Transaction.booked_at >= start, Transaction.booked_at <= end)
        .all()
    )


def strategy_out(row: MonthlyStrategy) -> MonthlyStrategyOut:
    invest = round(row.crypto_pct + row.stocks_pct + row.etfs_pct, 2)
    return MonthlyStrategyOut(
        year=row.year,
        month=row.month,
        crypto_pct=row.crypto_pct,
        stocks_pct=row.stocks_pct,
        etfs_pct=row.etfs_pct,
        save_pct=row.save_pct,
        spend_pct=row.spend_pct,
        invest_pct=invest,
    )


def get_or_create_strategy(db: Session, household_id: int, year: int, month: int) -> MonthlyStrategy:
    row = (
        db.query(MonthlyStrategy)
        .filter(MonthlyStrategy.household_id == household_id, MonthlyStrategy.year == year, MonthlyStrategy.month == month)
        .first()
    )
    if row is not None:
        return row
    row = MonthlyStrategy(
        household_id=household_id,
        year=year,
        month=month,
        crypto_pct=DEFAULT_CRYPTO_PCT,
        stocks_pct=DEFAULT_STOCKS_PCT,
        etfs_pct=DEFAULT_ETFS_PCT,
        save_pct=DEFAULT_SAVE_PCT,
        spend_pct=DEFAULT_SPEND_PCT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_monthly_summary(db: Session, household_id: int, year: int, month: int, txs: list[Transaction] | None = None, strategy: MonthlyStrategy | None = None) -> MonthlySummaryOut:
    _, end = month_bounds(year, month)
    strategy = strategy or get_or_create_strategy(db, household_id, year, month)
    invest_pct = strategy.crypto_pct + strategy.stocks_pct + strategy.etfs_pct
    txs = txs if txs is not None else month_transactions(db, household_id, year, month)
    income, real_spend, invest_out, save_amount = month_flow_totals(txs)
    save_pct = round((save_amount / income * 100), 1) if income else 0.0
    accounts = active_accounts(db, household_id)
    nw = net_worth_on(db, household_id, end, accounts)
    prev_month = month - 1 or 12
    prev_year = year if month > 1 else year - 1
    _, prev_last = month_bounds(prev_year, prev_month)
    prev_nw = net_worth_on(db, household_id, prev_last, accounts)
    delta_amount = round(nw - prev_nw, 2)
    delta = ((nw - prev_nw) / prev_nw * 100) if prev_nw else None
    actual_spend_pct = round((real_spend / income * 100), 1) if income else 0.0
    actual_invest_pct = round((invest_out / income * 100), 1) if income else 0.0
    actual_save_pct = round((save_amount / income * 100), 1) if income else 0.0
    return MonthlySummaryOut(
        year=year,
        month=month,
        income=income,
        real_spend=real_spend,
        save_amount=save_amount,
        save_pct=save_pct,
        net_worth=round(nw, 2),
        net_worth_delta=delta_amount,
        net_worth_delta_pct=round(delta, 2) if delta is not None else None,
        recommended_spend=round(income * strategy.spend_pct / 100, 2),
        recommended_save=round(income * strategy.save_pct / 100, 2),
        recommended_invest=round(income * invest_pct / 100, 2),
        actual_spend_pct=actual_spend_pct,
        actual_save_pct=actual_save_pct,
        actual_invest_pct=actual_invest_pct,
    )


def spend_by_category(txs: list[Transaction], benchmarks: dict[str, float] | None = None) -> list[CategorySpendOut]:
    totals: dict[tuple[int | None, str, str], float] = defaultdict(float)
    for tx in txs:
        if tx.amount >= 0:
            continue
        if tx.category and tx.category.kind in ("transfer", "investment"):
            continue
        key = (tx.category_id, tx.category.name if tx.category else "Uncategorized", tx.category.color if tx.category else "#9CA3AF")
        totals[key] += abs(tx.amount)
    total_spend = sum(totals.values()) or 1.0
    benchmarks = benchmarks or {}
    rows = []
    for k, v in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        bench = benchmarks.get(k[1])
        rows.append(
            CategorySpendOut(
                category_id=k[0],
                category_name=k[1],
                amount=round(v, 2),
                pct=round(v / total_spend * 100, 1),
                color=k[2],
                benchmark_amount=round(bench, 2) if bench is not None else None,
                benchmark_pct=round(bench / total_spend * 100, 1) if bench is not None and total_spend else None,
            )
        )
    return rows


def _month_ends(through_year: int, through_month: int, months: int = 12) -> list[tuple[str, date]]:
    points = []
    y, m = through_year, through_month
    for _ in range(months):
        _, end = month_bounds(y, m)
        points.append((f"{y}-{m:02d}", end))
        m -= 1
        if m <= 0:
            m = 12
            y -= 1
    points.reverse()
    return points


def wealth_series(db: Session, household_id: int, include_investments: bool, through_year: int, through_month: int, months: int = 12) -> list[dict]:
    accounts = active_accounts(db, household_id)
    if not include_investments:
        accounts = [a for a in accounts if a.account_type != AccountType.investment.value]
    points = [{"label": label, "value": round(sum(account_balance_on(db, a.id, end) for a in accounts), 2)} for label, end in _month_ends(through_year, through_month, months)]
    while len(points) > 2 and points[0]["value"] == 0:
        points.pop(0)
    return points


def iter_months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def build_month_rows(db: Session, household_id: int) -> list[MonthNavRowOut]:
    start = earliest_activity_month(db, household_id)
    end = latest_activity_month(db, household_id)
    if start is None or end is None:
        return []
    accounts = active_accounts(db, household_id)
    rows = []
    prev_nw = None
    for y, m in iter_months(start, end):
        txs = month_transactions(db, household_id, y, m)
        income, real_spend, invest_out, save_amount = month_flow_totals(txs)
        save_pct = round((save_amount / income * 100), 1) if income else 0.0
        _, month_end = month_bounds(y, m)
        nw = round(net_worth_on(db, household_id, month_end, accounts), 2)
        delta = round(((nw - prev_nw) / prev_nw * 100), 2) if prev_nw else None
        rows.append(MonthNavRowOut(year=y, month=m, label=month_label(y, m), income=income, real_spend=real_spend, save_pct=save_pct, net_worth=nw, net_worth_delta_pct=delta))
        prev_nw = nw
    return rows


def average_income_spend(db: Session, household_id: int) -> tuple[float, float]:
    rows = build_month_rows(db, household_id)
    active = [r for r in rows if r.income > 0 or r.real_spend > 0]
    if not active:
        return 0.0, 0.0
    avg_income = sum(r.income for r in active) / len(active)
    avg_spend = sum(r.real_spend for r in active) / len(active)
    return round(avg_income, 2), round(avg_spend, 2)


def build_wealth_projection(
    db: Session,
    household_id: int,
    strategy: MonthlyStrategy,
    through_year: int,
    through_month: int,
    years: int = 3,
) -> tuple[list[dict], dict]:
    avg_income, _ = average_income_spend(db, household_id)
    # Prefer the selected month's income when available so projection tracks the open statement.
    month_txs = month_transactions(db, household_id, through_year, through_month)
    month_income = round(sum(t.amount for t in month_txs if t.amount > 0), 2)
    base_income = month_income if month_income > 0 else avg_income
    accounts = active_accounts(db, household_id)
    _, as_of = month_bounds(through_year, through_month)
    invested = sum(account_balance_on(db, a.id, as_of) for a in accounts if a.account_type == AccountType.investment.value)
    total = sum(account_balance_on(db, a.id, as_of) for a in accounts)
    cash = max(total - invested, 0.0)
    spend_pct = strategy.spend_pct
    save_pct = strategy.save_pct
    invest_pct = strategy.crypto_pct + strategy.stocks_pct + strategy.etfs_pct
    # Month strategy drives planned spend / save / invest each projected month.
    monthly_spend = base_income * spend_pct / 100
    monthly_save = base_income * save_pct / 100
    monthly_invest = base_income * invest_pct / 100
    monthly_rate = (1 + SP500_ANNUAL_RETURN) ** (1 / 12) - 1
    points = [{"label": f"{through_year}-{through_month:02d}", "value": round(total, 2), "kind": "actual"}]
    y, m = through_year, through_month
    for _ in range(years * 12):
        m += 1
        if m > 12:
            m = 1
            y += 1
        cash += monthly_save
        invested = invested * (1 + monthly_rate) + monthly_invest
        points.append({"label": f"{y}-{m:02d}", "value": round(cash + invested, 2), "kind": "projected"})
    assumptions = {
        "avg_monthly_income": round(base_income, 2),
        "avg_monthly_spend": round(monthly_spend, 2),
        "spend_pct": round(spend_pct, 2),
        "save_pct": round(save_pct, 2),
        "invest_pct": round(invest_pct, 2),
        "sp500_annual_return_pct": round(SP500_ANNUAL_RETURN * 100, 1),
        "years": years,
    }
    return points, assumptions


def build_dashboard(db: Session, household_id: int, year: int | None = None, month: int | None = None) -> DashboardOut:
    today = date.today()
    if year is None or month is None:
        activity = latest_activity_month(db, household_id)
        year, month = activity if activity else (today.year, today.month)
    accounts = active_accounts(db, household_id)
    _, month_end = month_bounds(year, month)
    balances = {account.id: account_balance_on(db, account.id, month_end) for account in accounts}
    invested_total = round(sum(balances[account.id] for account in accounts if account.account_type == AccountType.investment.value), 2)
    txs = month_transactions(db, household_id, year, month)
    plan = db.query(IncomeAllocationPlan).filter(IncomeAllocationPlan.household_id == household_id).one()
    strategy = get_or_create_strategy(db, household_id, year, month)
    projection, assumptions = build_wealth_projection(db, household_id, strategy, year, month)
    month_income = round(sum(t.amount for t in txs if t.amount > 0), 2)
    avg_income, _ = average_income_spend(db, household_id)
    income_for_benchmark = month_income if month_income > 0 else avg_income
    household = db.get(Household, household_id)
    benchmarks, benchmark_source, benchmark_location = get_or_refresh_benchmarks(db, household, income_for_benchmark)
    account_outs = [
        AccountOut(id=a.id, name=a.name, institution=a.institution, currency=a.currency, account_type=a.account_type, source=a.source, is_active=a.is_active, latest_balance=balances.get(a.id, 0.0))
        for a in accounts
    ]
    return DashboardOut(
        net_worth=round(sum(balances.values()), 2),
        month=build_monthly_summary(db, household_id, year, month, txs, strategy),
        spend_by_category=spend_by_category(txs, benchmarks),
        accounts=account_outs,
        invested_total=invested_total,
        allocation=AllocationPlanOut.model_validate(plan),
        strategy=strategy_out(strategy),
        month_rows=build_month_rows(db, household_id),
        wealth_no_invest_series=wealth_series(db, household_id, include_investments=False, through_year=year, through_month=month),
        wealth_with_invest_series=wealth_series(db, household_id, include_investments=True, through_year=year, through_month=month),
        wealth_projection=projection,
        projection_assumptions=assumptions,
        benchmark_location=benchmark_location,
        benchmark_source=benchmark_source,
    )
