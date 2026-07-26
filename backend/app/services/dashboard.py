from calendar import monthrange
from datetime import date
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import Account, AccountType, BalanceSnapshot, IncomeAllocationPlan, Transaction, BankConnection
from app.schemas import AccountOut, AllocationPlanOut, BankConnectionOut, CategorySpendOut, DashboardOut, MonthlySummaryOut


def account_balance_on(db: Session, account_id: int, as_of: date) -> float:
    # Prefer snapshot as an anchor, then apply later txs so charts work without monthly snapshots.
    snap = (
        db.query(BalanceSnapshot)
        .filter(BalanceSnapshot.account_id == account_id, BalanceSnapshot.snapshot_date <= as_of)
        .order_by(BalanceSnapshot.snapshot_date.desc())
        .first()
    )
    if snap is None:
        total = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(Transaction.account_id == account_id, Transaction.booked_at <= as_of).scalar()
        return float(total)
    later = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(Transaction.account_id == account_id, Transaction.booked_at > snap.snapshot_date, Transaction.booked_at <= as_of).scalar()
    return float(snap.amount) + float(later)


def latest_balances(db: Session, household_id: int) -> dict[int, float]:
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()
    today = date.today()
    return {account.id: account_balance_on(db, account.id, today) for account in accounts}


def net_worth_on(db: Session, household_id: int, as_of: date) -> float:
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()
    return sum(account_balance_on(db, account.id, as_of) for account in accounts)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def latest_activity_month(db: Session, household_id: int) -> tuple[int, int] | None:
    account_ids = [a.id for a in db.query(Account).filter(Account.household_id == household_id).all()]
    if not account_ids:
        return None
    latest = db.query(Transaction.booked_at).filter(Transaction.account_id.in_(account_ids)).order_by(Transaction.booked_at.desc()).first()
    if latest is None:
        return None
    return latest[0].year, latest[0].month


def build_monthly_summary(db: Session, household_id: int, year: int, month: int) -> MonthlySummaryOut:
    start, end = month_bounds(year, month)
    plan = db.query(IncomeAllocationPlan).filter(IncomeAllocationPlan.household_id == household_id).one()
    account_ids = [a.id for a in db.query(Account).filter(Account.household_id == household_id).all()]
    txs = []
    if account_ids:
        txs = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.account_id.in_(account_ids), Transaction.booked_at >= start, Transaction.booked_at <= end).all()
    # Income = credits (salary and other inflows). Spend = abs(debits / negative amounts).
    income = round(sum(t.amount for t in txs if t.amount > 0), 2)
    real_spend = round(abs(sum(t.amount for t in txs if t.amount < 0)), 2)
    invest_out = round(abs(sum(t.amount for t in txs if t.amount < 0 and t.category is not None and t.category.kind == "investment")), 2)
    save_amount = round(income - real_spend, 2)
    save_pct = round((save_amount / income * 100), 1) if income else 0.0
    nw = net_worth_on(db, household_id, end)
    prev_month = month - 1 or 12
    prev_year = year if month > 1 else year - 1
    _, prev_last = month_bounds(prev_year, prev_month)
    prev_nw = net_worth_on(db, household_id, prev_last)
    delta = ((nw - prev_nw) / prev_nw * 100) if prev_nw else None
    actual_spend_pct = round((real_spend / income * 100), 1) if income else 0.0
    actual_invest_pct = round((invest_out / income * 100), 1) if income else 0.0
    actual_save_pct = round(100 - actual_spend_pct - actual_invest_pct, 1) if income else 0.0
    return MonthlySummaryOut(
        year=year,
        month=month,
        income=income,
        real_spend=real_spend,
        save_amount=save_amount,
        save_pct=save_pct,
        net_worth=round(nw, 2),
        net_worth_delta_pct=round(delta, 2) if delta is not None else None,
        recommended_spend=round(income * plan.spend_pct / 100, 2),
        recommended_save=round(income * plan.save_pct / 100, 2),
        recommended_invest=round(income * plan.invest_pct / 100, 2),
        actual_spend_pct=actual_spend_pct,
        actual_save_pct=actual_save_pct,
        actual_invest_pct=actual_invest_pct,
    )


def spend_by_category(db: Session, household_id: int, year: int, month: int) -> list[CategorySpendOut]:
    start, end = month_bounds(year, month)
    account_ids = [a.id for a in db.query(Account).filter(Account.household_id == household_id).all()]
    if not account_ids:
        return []
    txs = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.account_id.in_(account_ids), Transaction.booked_at >= start, Transaction.booked_at <= end, Transaction.amount < 0).all()
    totals: dict[tuple[int | None, str, str], float] = defaultdict(float)
    for tx in txs:
        if tx.category and tx.category.kind in ("transfer", "investment"):
            continue
        key = (tx.category_id, tx.category.name if tx.category else "Uncategorized", tx.category.color if tx.category else "#9CA3AF")
        totals[key] += abs(tx.amount)
    total_spend = sum(totals.values()) or 1.0
    return [
        CategorySpendOut(category_id=k[0], category_name=k[1], amount=round(v, 2), pct=round(v / total_spend * 100, 1), color=k[2])
        for k, v in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def net_worth_series(db: Session, household_id: int, months: int = 12) -> list[dict]:
    today = date.today()
    points = []
    for offset in range(months - 1, -1, -1):
        y = today.year
        m = today.month - offset
        while m <= 0:
            m += 12
            y -= 1
        _, end = month_bounds(y, m)
        points.append({"label": f"{y}-{m:02d}", "value": round(net_worth_on(db, household_id, end), 2)})
    return points


def wealth_series(db: Session, household_id: int, include_investments: bool, months: int = 12) -> list[dict]:
    today = date.today()
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()
    if not include_investments:
        accounts = [a for a in accounts if a.account_type != AccountType.investment.value]
    points = []
    for offset in range(months - 1, -1, -1):
        y = today.year
        m = today.month - offset
        while m <= 0:
            m += 12
            y -= 1
        _, end = month_bounds(y, m)
        total = sum(account_balance_on(db, account.id, end) for account in accounts)
        points.append({"label": f"{y}-{m:02d}", "value": round(total, 2)})
    return points


def build_dashboard(db: Session, household_id: int, year: int | None = None, month: int | None = None) -> DashboardOut:
    today = date.today()
    if year is None or month is None:
        activity = latest_activity_month(db, household_id)
        if activity:
            year, month = activity
        else:
            year, month = today.year, today.month
    balances = latest_balances(db, household_id)
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()
    account_outs = [
        AccountOut(
            id=a.id,
            name=a.name,
            institution=a.institution,
            currency=a.currency,
            account_type=a.account_type,
            source=a.source,
            is_active=a.is_active,
            latest_balance=balances.get(a.id, 0.0),
        )
        for a in accounts
    ]
    plan = db.query(IncomeAllocationPlan).filter(IncomeAllocationPlan.household_id == household_id).one()
    connections = db.query(BankConnection).filter(BankConnection.household_id == household_id).all()
    return DashboardOut(
        net_worth=round(sum(balances.values()), 2),
        month=build_monthly_summary(db, household_id, year, month),
        spend_by_category=spend_by_category(db, household_id, year, month),
        accounts=account_outs,
        allocation=AllocationPlanOut.model_validate(plan),
        net_worth_series=net_worth_series(db, household_id),
        wealth_no_invest_series=wealth_series(db, household_id, include_investments=False),
        wealth_with_invest_series=wealth_series(db, household_id, include_investments=True),
        connections=[BankConnectionOut.model_validate(c) for c in connections],
    )
