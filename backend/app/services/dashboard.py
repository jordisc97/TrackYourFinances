from calendar import monthrange
from collections import defaultdict
from datetime import date

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
    StrategyHistoryRowOut,
)
from app.services.benchmarks import get_or_refresh_benchmarks

SP500_ANNUAL_RETURN = 0.10
DEFAULT_CRYPTO_PCT = 10.0
DEFAULT_STOCKS_PCT = 10.0
DEFAULT_ETFS_PCT = 10.0
DEFAULT_SAVE_PCT = 40.0
DEFAULT_SPEND_PCT = 30.0
NON_SPEND_KINDS = ("transfer", "investment")
NON_INCOME_KINDS = ("transfer", "investment")
INCOME_KIND = "income"
CATALAN_MONTHS = ("gen", "feb", "març", "abr", "maig", "juny", "jul", "ago", "set", "oct", "nov", "des")


def category_kind(tx: Transaction) -> str | None:
    return tx.category.kind if tx.category is not None else None


def is_spend_outflow(tx: Transaction) -> bool:
    return tx.amount < 0 and category_kind(tx) not in NON_SPEND_KINDS


def is_invest_outflow(tx: Transaction) -> bool:
    return tx.amount < 0 and category_kind(tx) == "investment"


def is_income_inflow(tx: Transaction) -> bool:
    return tx.amount > 0 and category_kind(tx) not in NON_INCOME_KINDS


def is_wage_inflow(tx: Transaction) -> bool:
    return tx.amount > 0 and category_kind(tx) == INCOME_KIND


def month_wage_total(txs: list[Transaction]) -> float:
    return round(sum(t.amount for t in txs if is_wage_inflow(t)), 2)


def month_flow_totals(txs: list[Transaction]) -> tuple[float, float, float, float]:
    income = round(sum(t.amount for t in txs if is_income_inflow(t)), 2)
    real_spend = round(abs(sum(t.amount for t in txs if is_spend_outflow(t))), 2)
    invest_out = round(abs(sum(t.amount for t in txs if is_invest_outflow(t))), 2)
    save_amount = round(income - real_spend - invest_out, 2)
    return income, real_spend, invest_out, save_amount


def month_table_flow(txs: list[Transaction]) -> tuple[float, float, float, float, float, float]:
    wage = month_wage_total(txs)
    _, real_spend, invest_out, _ = month_flow_totals(txs)
    save_amount = round(wage - real_spend - invest_out, 2)
    save_pct = round((save_amount / wage * 100), 1) if wage else 0.0
    month_surplus = round(wage - real_spend, 2)
    return wage, real_spend, invest_out, save_amount, save_pct, month_surplus


def month_row_lookup(month_rows: list[MonthNavRowOut], year: int, month: int) -> MonthNavRowOut | None:
    return next((row for row in month_rows if row.year == year and row.month == month), None)


def month_rows_wealth_series(month_rows: list[MonthNavRowOut], through_year: int, through_month: int, months: int = 12) -> list[dict]:
    by_key = {(row.year, row.month): row for row in month_rows}
    points = []
    for label, _ in _month_ends(through_year, through_month, months):
        y, m = int(label[:4]), int(label[5:7])
        row = by_key.get((y, m))
        points.append({"label": label, "value": round(row.net_worth, 2) if row is not None else 0.0})
    while len(points) > 2 and points[0]["value"] == 0:
        points.pop(0)
    return points


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def month_label(year: int, month: int) -> str:
    return f"{CATALAN_MONTHS[month - 1]}-{str(year)[2:]}"


def _account_tx_sums_through(db: Session, account_ids: list[int]) -> dict[int, list[tuple[date, float]]]:
    if not account_ids:
        return {}
    rows = (
        db.query(Transaction.account_id, Transaction.booked_at, Transaction.amount)
        .filter(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.booked_at.asc())
        .all()
    )
    by_account: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for account_id, booked_at, amount in rows:
        by_account[account_id].append((booked_at, float(amount)))
    return by_account


def _opening_snapshots(db: Session, account_ids: list[int], earliest_by_account: dict[int, date]) -> dict[int, float]:
    openings = {account_id: 0.0 for account_id in account_ids}
    if not account_ids:
        return openings
    snaps = db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id.in_(account_ids)).order_by(BalanceSnapshot.snapshot_date.desc()).all()
    seen: set[int] = set()
    for snap in snaps:
        if snap.account_id in seen:
            continue
        earliest = earliest_by_account.get(snap.account_id)
        if earliest is not None and snap.snapshot_date < earliest:
            openings[snap.account_id] = float(snap.amount)
            seen.add(snap.account_id)
    return openings


def account_balances_on_dates(db: Session, accounts: list[Account], as_of_dates: list[date]) -> dict[date, dict[int, float]]:
    account_ids = [a.id for a in accounts]
    tx_lists = _account_tx_sums_through(db, account_ids)
    earliest = {account_id: rows[0][0] for account_id, rows in tx_lists.items() if rows}
    openings = _opening_snapshots(db, account_ids, earliest)
    latest_snap: dict[int, list[tuple[date, float]]] = defaultdict(list)
    if account_ids:
        for snap in db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id.in_(account_ids)).order_by(BalanceSnapshot.snapshot_date.asc()).all():
            latest_snap[snap.account_id].append((snap.snapshot_date, float(snap.amount)))
    result: dict[date, dict[int, float]] = {as_of: {} for as_of in as_of_dates}
    for account in accounts:
        rows = tx_lists.get(account.id, [])
        opening = openings.get(account.id, 0.0)
        idx = 0
        running = opening
        snap_rows = latest_snap.get(account.id, [])
        snap_idx = 0
        snap_balance = 0.0
        for as_of in sorted(as_of_dates):
            while idx < len(rows) and rows[idx][0] <= as_of:
                running += rows[idx][1]
                idx += 1
            while snap_idx < len(snap_rows) and snap_rows[snap_idx][0] <= as_of:
                snap_balance = snap_rows[snap_idx][1]
                snap_idx += 1
            earliest_tx = earliest.get(account.id)
            if earliest_tx is not None and earliest_tx <= as_of:
                result[as_of][account.id] = running
            else:
                result[as_of][account.id] = snap_balance
    return result


def account_balance_on(db: Session, account_id: int, as_of: date) -> float:
    account = db.get(Account, account_id)
    if account is None:
        return 0.0
    return account_balances_on_dates(db, [account], [as_of])[as_of].get(account_id, 0.0)


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


def household_transactions(db: Session, household_id: int) -> list[Transaction]:
    account_ids = household_account_ids(db, household_id)
    if not account_ids:
        return []
    return (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.booked_at.asc())
        .all()
    )


def month_transactions(db: Session, household_id: int, year: int, month: int, all_txs: list[Transaction] | None = None) -> list[Transaction]:
    if all_txs is not None:
        return [tx for tx in all_txs if tx.booked_at.year == year and tx.booked_at.month == month]
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


def build_monthly_summary(db: Session, household_id: int, year: int, month: int, txs: list[Transaction] | None = None, strategy: MonthlyStrategy | None = None, month_rows: list[MonthNavRowOut] | None = None) -> MonthlySummaryOut:
    strategy = strategy or get_or_create_strategy(db, household_id, year, month)
    invest_pct = strategy.crypto_pct + strategy.stocks_pct + strategy.etfs_pct
    txs = txs if txs is not None else month_transactions(db, household_id, year, month)
    wage, real_spend, invest_out, save_amount, save_pct, _ = month_table_flow(txs)
    prev_month = month - 1 or 12
    prev_year = year if month > 1 else year - 1
    current_row = month_row_lookup(month_rows or [], year, month) if month_rows is not None else None
    prev_row = month_row_lookup(month_rows or [], prev_year, prev_month) if month_rows is not None else None
    nw = round(current_row.net_worth, 2) if current_row is not None else 0.0
    delta_amount = round(nw - prev_row.net_worth, 2) if prev_row is not None else 0.0
    delta_pct = current_row.net_worth_delta_pct if current_row is not None else None
    actual_spend_pct = round((real_spend / wage * 100), 1) if wage else 0.0
    actual_invest_pct = round((invest_out / wage * 100), 1) if wage else 0.0
    actual_save_pct = round((save_amount / wage * 100), 1) if wage else 0.0
    return MonthlySummaryOut(
        year=year,
        month=month,
        income=wage,
        real_spend=real_spend,
        save_amount=save_amount,
        save_pct=save_pct,
        net_worth=nw,
        net_worth_delta=delta_amount,
        net_worth_delta_pct=delta_pct,
        recommended_spend=round(wage * strategy.spend_pct / 100, 2),
        recommended_save=round(wage * strategy.save_pct / 100, 2),
        recommended_invest=round(wage * invest_pct / 100, 2),
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
    ends = _month_ends(through_year, through_month, months)
    balances_by_date = account_balances_on_dates(db, accounts, [end for _, end in ends])
    points = [{"label": label, "value": round(sum(balances_by_date[end].values()), 2)} for label, end in ends]
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


def build_month_rows(db: Session, household_id: int, all_txs: list[Transaction] | None = None) -> list[MonthNavRowOut]:
    txs = all_txs if all_txs is not None else household_transactions(db, household_id)
    if not txs:
        return []
    by_month: dict[tuple[int, int], list[Transaction]] = defaultdict(list)
    for tx in txs:
        by_month[(tx.booked_at.year, tx.booked_at.month)].append(tx)
    start = min(by_month)
    end = max(by_month)
    rows = []
    prev_wealth = None
    for y, m in iter_months(start, end):
        month_txs = by_month.get((y, m), [])
        wage, real_spend, invest_out, save_amount, save_pct, month_surplus = month_table_flow(month_txs)
        wealth = round(month_surplus if prev_wealth is None else prev_wealth + month_surplus, 2)
        delta = round(((wealth - prev_wealth) / abs(prev_wealth) * 100), 2) if prev_wealth else None
        rows.append(MonthNavRowOut(year=y, month=m, label=month_label(y, m), income=wage, real_spend=real_spend, save_pct=save_pct, net_worth=wealth, net_worth_delta_pct=delta))
        prev_wealth = wealth
    return rows


def build_strategy_history(db: Session, household_id: int, month_rows: list[MonthNavRowOut]) -> list[StrategyHistoryRowOut]:
    strategies = db.query(MonthlyStrategy).filter(MonthlyStrategy.household_id == household_id).all()
    by_key = {(row.year, row.month): row for row in strategies}
    history: list[StrategyHistoryRowOut] = []
    for month_row in reversed(month_rows):
        stored = by_key.get((month_row.year, month_row.month))
        spend_pct = float(stored.spend_pct) if stored is not None else DEFAULT_SPEND_PCT
        save_pct = float(stored.save_pct) if stored is not None else DEFAULT_SAVE_PCT
        invest_pct = round(float(stored.crypto_pct + stored.stocks_pct + stored.etfs_pct), 2) if stored is not None else round(DEFAULT_CRYPTO_PCT + DEFAULT_STOCKS_PCT + DEFAULT_ETFS_PCT, 2)
        salary = float(month_row.income)
        history.append(
            StrategyHistoryRowOut(
                year=month_row.year,
                month=month_row.month,
                label=month_row.label,
                salary=salary,
                spend=round(salary * spend_pct / 100, 2),
                save=round(salary * save_pct / 100, 2),
                invest=round(salary * invest_pct / 100, 2),
                spend_pct=spend_pct,
                save_pct=save_pct,
                invest_pct=invest_pct,
            )
        )
    return history


def average_income_spend(db: Session, household_id: int, month_rows: list[MonthNavRowOut] | None = None) -> tuple[float, float]:
    rows = month_rows if month_rows is not None else build_month_rows(db, household_id)
    active = [r for r in rows if r.income > 0 or r.real_spend > 0]
    if not active:
        return 0.0, 0.0
    avg_income = sum(r.income for r in active) / len(active)
    avg_spend = sum(r.real_spend for r in active) / len(active)
    return round(avg_income, 2), round(avg_spend, 2)


def _project_forward_from_wealth(start_wealth: float, base_income: float, spend_pct: float, save_pct: float, invest_pct: float, through_year: int, through_month: int, months: int) -> list[dict]:
    monthly_save = base_income * save_pct / 100
    monthly_invest = base_income * invest_pct / 100
    monthly_rate = (1 + SP500_ANNUAL_RETURN) ** (1 / 12) - 1
    wealth = start_wealth
    invested = 0.0
    points: list[dict] = [{"label": f"{through_year}-{through_month:02d}", "value": round(wealth + invested, 2), "kind": "actual"}]
    y, m = through_year, through_month
    for _ in range(months):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        wealth += monthly_save
        invested = invested * (1 + monthly_rate) + monthly_invest
        points.append({"label": f"{y}-{m:02d}", "value": round(wealth + invested, 2), "kind": "projected"})
    return points


def _project_forward_no_invest_from_wealth(start_wealth: float, base_income: float, save_pct: float, invest_pct: float, through_year: int, through_month: int, months: int) -> list[dict]:
    monthly_surplus = base_income * (save_pct + invest_pct) / 100
    wealth = start_wealth
    points: list[dict] = [{"label": f"{through_year}-{through_month:02d}", "value": round(wealth, 2), "kind": "actual"}]
    y, m = through_year, through_month
    for _ in range(months):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        wealth += monthly_surplus
        points.append({"label": f"{y}-{m:02d}", "value": round(wealth, 2), "kind": "projected"})
    return points


def build_wealth_projection(
    db: Session,
    household_id: int,
    strategy: MonthlyStrategy,
    through_year: int,
    through_month: int,
    month_rows: list[MonthNavRowOut] | None = None,
    month_txs: list[Transaction] | None = None,
) -> tuple[list[dict], list[dict], dict]:
    avg_income, _ = average_income_spend(db, household_id, month_rows)
    month_txs = month_txs if month_txs is not None else month_transactions(db, household_id, through_year, through_month)
    month_wage = month_wage_total(month_txs)
    base_income = month_wage if month_wage > 0 else avg_income
    current_row = month_row_lookup(month_rows or [], through_year, through_month) if month_rows is not None else None
    start_wealth = round(current_row.net_worth, 2) if current_row is not None else 0.0
    spend_pct = strategy.spend_pct
    save_pct = strategy.save_pct
    invest_pct = strategy.crypto_pct + strategy.stocks_pct + strategy.etfs_pct
    points = _project_forward_from_wealth(start_wealth, base_income, spend_pct, save_pct, invest_pct, through_year, through_month, 12)
    points_no_invest = _project_forward_no_invest_from_wealth(start_wealth, base_income, save_pct, invest_pct, through_year, through_month, 12)
    assumptions = {
        "avg_monthly_income": round(base_income, 2),
        "avg_monthly_spend": round(base_income * spend_pct / 100, 2),
        "spend_pct": round(spend_pct, 2),
        "save_pct": round(save_pct, 2),
        "invest_pct": round(invest_pct, 2),
        "sp500_annual_return_pct": round(SP500_ANNUAL_RETURN * 100, 1),
        "years": 1,
    }
    return points, points_no_invest, assumptions


def build_dashboard(db: Session, household_id: int, year: int | None = None, month: int | None = None) -> DashboardOut:
    today = date.today()
    all_txs = household_transactions(db, household_id)
    month_rows = build_month_rows(db, household_id, all_txs)
    if year is None or month is None:
        if month_rows:
            year, month = month_rows[-1].year, month_rows[-1].month
        else:
            year, month = today.year, today.month
    accounts = active_accounts(db, household_id)
    ends = [month_bounds(year, month)[1]]
    prev_month = month - 1 or 12
    prev_year = year if month > 1 else year - 1
    ends.append(month_bounds(prev_year, prev_month)[1])
    for _, end in _month_ends(year, month, 12):
        ends.append(end)
    unique_ends = sorted(set(ends))
    balances_by_date = account_balances_on_dates(db, accounts, unique_ends)
    month_end = month_bounds(year, month)[1]
    balances = balances_by_date[month_end]
    invested_total = round(sum(balances[account.id] for account in accounts if account.account_type == AccountType.investment.value), 2)
    txs = month_transactions(db, household_id, year, month, all_txs)
    plan = db.query(IncomeAllocationPlan).filter(IncomeAllocationPlan.household_id == household_id).one()
    strategy = get_or_create_strategy(db, household_id, year, month)
    projection, projection_no_invest, assumptions = build_wealth_projection(
        db, household_id, strategy, year, month, month_rows=month_rows, month_txs=txs
    )
    month_income = month_wage_total(txs)
    avg_income, _ = average_income_spend(db, household_id, month_rows)
    income_for_benchmark = month_income if month_income > 0 else avg_income
    household = db.get(Household, household_id)
    benchmarks, benchmark_source, benchmark_location = get_or_refresh_benchmarks(db, household, income_for_benchmark)
    account_outs = [
        AccountOut(id=a.id, name=a.name, institution=a.institution, currency=a.currency, account_type=a.account_type, source=a.source, is_active=a.is_active, latest_balance=balances.get(a.id, 0.0))
        for a in accounts
    ]
    wealth_series_data = month_rows_wealth_series(month_rows, year, month, 12)
    selected_row = month_row_lookup(month_rows, year, month)

    return DashboardOut(
        net_worth=round(selected_row.net_worth, 2) if selected_row is not None else 0.0,
        month=build_monthly_summary(db, household_id, year, month, txs, strategy, month_rows),
        spend_by_category=spend_by_category(txs, benchmarks),
        accounts=account_outs,
        invested_total=invested_total,
        allocation=AllocationPlanOut.model_validate(plan),
        strategy=strategy_out(strategy),
        month_rows=month_rows,
        strategy_history=build_strategy_history(db, household_id, month_rows),
        wealth_no_invest_series=wealth_series_data,
        wealth_with_invest_series=wealth_series_data,
        wealth_projection=projection,
        wealth_projection_no_invest=projection_no_invest,
        projection_assumptions=assumptions,
        benchmark_location=benchmark_location,
        benchmark_source=benchmark_source,
    )
