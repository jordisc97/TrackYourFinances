from calendar import monthrange
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Account, AccountType, BalanceSnapshot, Household, MonthlyInvestmentReal, MonthlyStrategy, MonthlyWealthBase, Transaction, TransactionSplit, YearlyWealthObjective
from app.schemas import (
    AccountOut,
    CategorySpendOut,
    DashboardOut,
    InvestmentMonthRowOut,
    InvestmentRealOut,
    MonthNavRowOut,
    MonthlyStrategyOut,
    MonthlySummaryOut,
    OpeningWealthOut,
    YearlyObjectiveOut,
)
from app.services.benchmarks import get_or_refresh_benchmarks

SP500_ANNUAL_RETURN = 0.10
NON_SPEND_KINDS = ("transfer", "investment")
NON_INCOME_KINDS = ("transfer", "investment")
INCOME_KIND = "income"
CATALAN_MONTHS = ("gen", "feb", "març", "abr", "maig", "juny", "jul", "ago", "set", "oct", "nov", "des")


def category_kind(tx: Transaction) -> str | None:
    return tx.category.kind if tx.category is not None else None


def split_kind(split) -> str | None:
    if split.category is not None:
        return split.category.kind
    return None


def tx_has_splits(tx: Transaction) -> bool:
    return bool(getattr(tx, "splits", None))


def spend_amount(tx: Transaction) -> float:
    if not tx_has_splits(tx):
        return tx.amount if is_spend_outflow(tx) else 0.0
    total = 0.0
    for split in tx.splits:
        kind = split_kind(split) if split.category is not None else category_kind(tx)
        if split.amount < 0 and kind not in NON_SPEND_KINDS:
            total += split.amount
    return total


def invest_amount(tx: Transaction) -> float:
    if not tx_has_splits(tx):
        return tx.amount if is_invest_outflow(tx) else 0.0
    total = 0.0
    for split in tx.splits:
        kind = split_kind(split) if split.category is not None else category_kind(tx)
        if split.amount < 0 and kind == "investment":
            total += split.amount
    return total


def is_spend_outflow(tx: Transaction) -> bool:
    if tx_has_splits(tx):
        return spend_amount(tx) < 0
    return tx.amount < 0 and category_kind(tx) not in NON_SPEND_KINDS


def is_invest_outflow(tx: Transaction) -> bool:
    if tx_has_splits(tx):
        return invest_amount(tx) < 0
    return tx.amount < 0 and category_kind(tx) == "investment"


def is_income_inflow(tx: Transaction) -> bool:
    return tx.amount > 0 and category_kind(tx) not in NON_INCOME_KINDS


def is_wage_inflow(tx: Transaction) -> bool:
    return tx.amount > 0 and category_kind(tx) == INCOME_KIND


def month_wage_total(txs: list[Transaction]) -> float:
    return round(sum(t.amount for t in txs if is_wage_inflow(t)), 2)


def month_flow_totals(txs: list[Transaction]) -> tuple[float, float, float, float]:
    income = round(sum(t.amount for t in txs if is_income_inflow(t)), 2)
    real_spend = round(abs(sum(spend_amount(t) for t in txs)), 2)
    invest_out = round(abs(sum(invest_amount(t) for t in txs)), 2)
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
        .options(joinedload(Transaction.category), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
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
        .options(joinedload(Transaction.category), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
        .filter(Transaction.account_id.in_(account_ids), Transaction.booked_at >= start, Transaction.booked_at <= end)
        .all()
    )


def strategy_out(row: MonthlyStrategy) -> MonthlyStrategyOut:
    return MonthlyStrategyOut(year=row.year, month=row.month, save_pct=row.save_pct, spend_pct=row.spend_pct, invest_pct=row.invest_pct)


def get_or_create_strategy(db: Session, household_id: int, year: int, month: int) -> MonthlyStrategy:
    row = (
        db.query(MonthlyStrategy)
        .filter(MonthlyStrategy.household_id == household_id, MonthlyStrategy.year == year, MonthlyStrategy.month == month)
        .first()
    )
    if row is not None:
        return row
    settings = get_settings()
    row = MonthlyStrategy(household_id=household_id, year=year, month=month, spend_pct=settings.default_spend_pct, save_pct=settings.default_save_pct, invest_pct=settings.default_invest_pct)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def investment_real_map(db: Session, household_id: int) -> dict[tuple[int, int], float | None]:
    rows = db.query(MonthlyInvestmentReal).filter(MonthlyInvestmentReal.household_id == household_id).all()
    return {(row.year, row.month): row.real_value for row in rows}


def get_or_create_investment_real(db: Session, household_id: int, year: int, month: int) -> MonthlyInvestmentReal:
    row = (
        db.query(MonthlyInvestmentReal)
        .filter(MonthlyInvestmentReal.household_id == household_id, MonthlyInvestmentReal.year == year, MonthlyInvestmentReal.month == month)
        .first()
    )
    if row is not None:
        return row
    row = MonthlyInvestmentReal(household_id=household_id, year=year, month=month, real_value=None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_investment_real(db: Session, household_id: int, year: int, month: int, real_value: float | None) -> InvestmentRealOut:
    row = get_or_create_investment_real(db, household_id, year, month)
    row.real_value = real_value
    db.commit()
    db.refresh(row)
    return InvestmentRealOut(year=row.year, month=row.month, real_value=row.real_value)


def yearly_objective_map(db: Session, household_id: int) -> dict[int, float]:
    rows = db.query(YearlyWealthObjective).filter(YearlyWealthObjective.household_id == household_id).all()
    return {row.year: row.target_net_worth for row in rows}


def get_or_create_yearly_objective(db: Session, household_id: int, year: int) -> YearlyWealthObjective:
    row = db.query(YearlyWealthObjective).filter(YearlyWealthObjective.household_id == household_id, YearlyWealthObjective.year == year).first()
    if row is not None:
        return row
    row = YearlyWealthObjective(household_id=household_id, year=year, target_net_worth=0.0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_yearly_objective(db: Session, household_id: int, year: int, target_net_worth: float) -> YearlyWealthObjective:
    row = get_or_create_yearly_objective(db, household_id, year)
    row.target_net_worth = target_net_worth
    db.commit()
    db.refresh(row)
    return row


def monthly_sp500_rate() -> float:
    return (1 + SP500_ANNUAL_RETURN) ** (1 / 12) - 1


def build_investment_month_rows(
    db: Session,
    household_id: int,
    month_rows: list[MonthNavRowOut],
    all_txs: list[Transaction] | None = None,
) -> list[InvestmentMonthRowOut]:
    txs = all_txs if all_txs is not None else household_transactions(db, household_id)
    by_month: dict[tuple[int, int], list[Transaction]] = defaultdict(list)
    for tx in txs:
        by_month[(tx.booked_at.year, tx.booked_at.month)].append(tx)
    reals = investment_real_map(db, household_id)
    rate = monthly_sp500_rate()
    accum = 0.0
    cum_invest = 0.0
    rows: list[InvestmentMonthRowOut] = []
    for nav in month_rows:
        month_txs = by_month.get((nav.year, nav.month), [])
        _, _, invest_out, _, _, _ = month_table_flow(month_txs)
        wage = nav.income
        invest_pct = round((invest_out / wage * 100), 1) if wage else 0.0
        accum = round(accum * (1 + rate) + invest_out, 2)
        cum_invest = round(cum_invest + invest_out, 2)
        rows.append(
            InvestmentMonthRowOut(
                year=nav.year,
                month=nav.month,
                label=f"{nav.year}-{nav.month:02d}",
                investment_amount=invest_out,
                investment_pct=invest_pct,
                accum_value=accum,
                real_value=reals.get((nav.year, nav.month)),
                cum_invest=cum_invest,
            )
        )
    return rows


def adjusted_net_worth(cashflow_wealth: float, cum_invest: float, real_value: float | None) -> float:
    if real_value is None:
        return round(cashflow_wealth, 2)
    return round(cashflow_wealth - cum_invest + real_value, 2)


def investment_row_lookup(rows: list[InvestmentMonthRowOut], year: int, month: int) -> InvestmentMonthRowOut | None:
    return next((row for row in rows if row.year == year and row.month == month), None)


def month_rows_wealth_series_adjusted(
    month_rows: list[MonthNavRowOut],
    invest_rows: list[InvestmentMonthRowOut],
    through_year: int,
    through_month: int,
    months: int = 12,
) -> list[dict]:
    by_key = {(row.year, row.month): row for row in month_rows}
    invest_by_key = {(row.year, row.month): row for row in invest_rows}
    points = []
    for label, _ in _month_ends(through_year, through_month, months):
        y, m = int(label[:4]), int(label[5:7])
        row = by_key.get((y, m))
        invest = invest_by_key.get((y, m))
        if row is None:
            points.append({"label": label, "value": 0.0})
            continue
        cum = invest.cum_invest if invest is not None else 0.0
        real = invest.real_value if invest is not None else None
        points.append({"label": label, "value": adjusted_net_worth(row.net_worth, cum, real)})
    while len(points) > 2 and points[0]["value"] == 0:
        points.pop(0)
    return points


def seed_invested_from_rows(invest_rows: list[InvestmentMonthRowOut], through_year: int, through_month: int) -> float:
    latest_real = None
    latest_accum = 0.0
    for row in invest_rows:
        if (row.year, row.month) > (through_year, through_month):
            break
        latest_accum = row.accum_value
        if row.real_value is not None:
            latest_real = row.real_value
    return round(latest_real if latest_real is not None else latest_accum, 2)


def months_until(from_year: int, from_month: int, to_year: int, to_month: int) -> int:
    return (to_year - from_year) * 12 + (to_month - from_month)

def build_monthly_summary(db: Session, household_id: int, year: int, month: int, txs: list[Transaction] | None = None, strategy: MonthlyStrategy | None = None, month_rows: list[MonthNavRowOut] | None = None) -> MonthlySummaryOut:
    strategy = strategy or get_or_create_strategy(db, household_id, year, month)
    invest_pct = strategy.invest_pct
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
        if tx_has_splits(tx):
            for split in tx.splits:
                kind = split_kind(split) if split.category is not None else category_kind(tx)
                if split.amount >= 0 or kind in NON_SPEND_KINDS:
                    continue
                cat = split.category if split.category is not None else tx.category
                key = (cat.id if cat else None, cat.name if cat else "Uncategorized", cat.color if cat else "#9CA3AF")
                totals[key] += abs(split.amount)
            continue
        if not is_spend_outflow(tx):
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


def iter_months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def wealth_base_for(db: Session, household_id: int, year: int, month: int) -> float | None:
    row = (
        db.query(MonthlyWealthBase)
        .filter(MonthlyWealthBase.household_id == household_id, MonthlyWealthBase.year == year, MonthlyWealthBase.month == month)
        .first()
    )
    return None if row is None else float(row.net_worth)


def get_or_create_wealth_base(db: Session, household_id: int, year: int, month: int) -> MonthlyWealthBase:
    row = (
        db.query(MonthlyWealthBase)
        .filter(MonthlyWealthBase.household_id == household_id, MonthlyWealthBase.year == year, MonthlyWealthBase.month == month)
        .first()
    )
    if row is not None:
        return row
    row = MonthlyWealthBase(household_id=household_id, year=year, month=month, net_worth=0.0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_opening_wealth(db: Session, household_id: int, year: int, month: int, net_worth: float) -> OpeningWealthOut:
    row = get_or_create_wealth_base(db, household_id, year, month)
    row.net_worth = net_worth
    db.commit()
    db.refresh(row)
    return OpeningWealthOut(year=row.year, month=row.month, net_worth=row.net_worth)


def build_month_rows(db: Session, household_id: int, all_txs: list[Transaction] | None = None) -> list[MonthNavRowOut]:
    txs = all_txs if all_txs is not None else household_transactions(db, household_id)
    if not txs:
        return []
    by_month: dict[tuple[int, int], list[Transaction]] = defaultdict(list)
    for tx in txs:
        by_month[(tx.booked_at.year, tx.booked_at.month)].append(tx)
    start = min(by_month)
    end = max(by_month)
    opening = wealth_base_for(db, household_id, start[0], start[1])
    rows = []
    prev_wealth = None
    for y, m in iter_months(start, end):
        month_txs = by_month.get((y, m), [])
        wage, real_spend, invest_out, save_amount, save_pct, month_surplus = month_table_flow(month_txs)
        is_opening = prev_wealth is None
        if is_opening and opening is not None:
            wealth = round(opening, 2)
        else:
            wealth = round(month_surplus if prev_wealth is None else prev_wealth + month_surplus, 2)
        delta = round(((wealth - prev_wealth) / abs(prev_wealth) * 100), 2) if prev_wealth else None
        rows.append(MonthNavRowOut(year=y, month=m, label=month_label(y, m), income=wage, real_spend=real_spend, save_pct=save_pct, net_worth=wealth, net_worth_delta_pct=delta, is_opening=is_opening))
        prev_wealth = wealth
    return rows


def average_income_spend(db: Session, household_id: int, month_rows: list[MonthNavRowOut] | None = None) -> tuple[float, float]:
    rows = month_rows if month_rows is not None else build_month_rows(db, household_id)
    active = [r for r in rows if r.income > 0 or r.real_spend > 0]
    if not active:
        return 0.0, 0.0
    avg_income = sum(r.income for r in active) / len(active)
    avg_spend = sum(r.real_spend for r in active) / len(active)
    return round(avg_income, 2), round(avg_spend, 2)


def _project_forward_from_wealth(
    start_wealth: float,
    base_income: float,
    spend_pct: float,
    save_pct: float,
    invest_pct: float,
    through_year: int,
    through_month: int,
    months: int,
    start_invested: float = 0.0,
) -> list[dict]:
    monthly_save = base_income * save_pct / 100
    monthly_invest = base_income * invest_pct / 100
    monthly_rate = monthly_sp500_rate()
    invested = start_invested
    wealth = start_wealth - invested
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


def build_yearly_objectives(
    db: Session,
    household_id: int,
    base_year: int,
    month_rows: list[MonthNavRowOut],
    invest_rows: list[InvestmentMonthRowOut],
    long_projection: list[dict],
) -> list[YearlyObjectiveOut]:
    targets = yearly_objective_map(db, household_id)
    invest_by_key = {(row.year, row.month): row for row in invest_rows}
    nav_by_key = {(row.year, row.month): row for row in month_rows}
    proj_by_label = {point["label"]: point["value"] for point in long_projection}
    objectives: list[YearlyObjectiveOut] = []
    for offset in range(3):
        year = base_year + offset
        dec_nav = nav_by_key.get((year, 12))
        dec_invest = invest_by_key.get((year, 12))
        actual = None
        if dec_nav is not None:
            cum = dec_invest.cum_invest if dec_invest is not None else 0.0
            real = dec_invest.real_value if dec_invest is not None else None
            actual = adjusted_net_worth(dec_nav.net_worth, cum, real)
        forecast = proj_by_label.get(f"{year}-12")
        target = targets.get(year)
        objectives.append(
            YearlyObjectiveOut(
                year=year,
                target_net_worth=target,
                forecast_year_end=round(forecast, 2) if forecast is not None else None,
                actual_net_worth=actual,
            )
        )
    return objectives


def build_wealth_projection(
    db: Session,
    household_id: int,
    strategy: MonthlyStrategy,
    through_year: int,
    through_month: int,
    month_rows: list[MonthNavRowOut] | None = None,
    month_txs: list[Transaction] | None = None,
    invest_rows: list[InvestmentMonthRowOut] | None = None,
    chart_months: int = 12,
    long_end_year: int | None = None,
) -> tuple[list[dict], list[dict], dict, list[dict]]:
    avg_income, _ = average_income_spend(db, household_id, month_rows)
    month_txs = month_txs if month_txs is not None else month_transactions(db, household_id, through_year, through_month)
    month_wage = month_wage_total(month_txs)
    base_income = month_wage if month_wage > 0 else avg_income
    current_row = month_row_lookup(month_rows or [], through_year, through_month) if month_rows is not None else None
    invest = investment_row_lookup(invest_rows or [], through_year, through_month) if invest_rows else None
    cashflow = round(current_row.net_worth, 2) if current_row is not None else 0.0
    cum = invest.cum_invest if invest is not None else 0.0
    real = invest.real_value if invest is not None else None
    start_wealth = adjusted_net_worth(cashflow, cum, real)
    start_invested = seed_invested_from_rows(invest_rows or [], through_year, through_month)
    spend_pct = strategy.spend_pct
    save_pct = strategy.save_pct
    invest_pct = strategy.invest_pct
    end_year = long_end_year if long_end_year is not None else through_year + 2
    long_months = max(chart_months, months_until(through_year, through_month, end_year, 12))
    long_points = _project_forward_from_wealth(start_wealth, base_income, spend_pct, save_pct, invest_pct, through_year, through_month, long_months, start_invested)
    points = long_points[: chart_months + 1]
    points_no_invest = _project_forward_no_invest_from_wealth(start_wealth, base_income, save_pct, invest_pct, through_year, through_month, chart_months)
    assumptions = {
        "avg_monthly_income": round(base_income, 2),
        "avg_monthly_spend": round(base_income * spend_pct / 100, 2),
        "spend_pct": round(spend_pct, 2),
        "save_pct": round(save_pct, 2),
        "invest_pct": round(invest_pct, 2),
        "sp500_annual_return_pct": round(SP500_ANNUAL_RETURN * 100, 1),
        "years": 1,
    }
    return points, points_no_invest, assumptions, long_points


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
    strategy = get_or_create_strategy(db, household_id, year, month)
    invest_rows = build_investment_month_rows(db, household_id, month_rows, all_txs)
    projection, projection_no_invest, assumptions, long_projection = build_wealth_projection(
        db, household_id, strategy, year, month, month_rows=month_rows, month_txs=txs, invest_rows=invest_rows, long_end_year=year + 2
    )
    yearly_objectives = build_yearly_objectives(db, household_id, year, month_rows, invest_rows, long_projection)
    month_income = month_wage_total(txs)
    avg_income, _ = average_income_spend(db, household_id, month_rows)
    income_for_benchmark = month_income if month_income > 0 else avg_income
    household = db.get(Household, household_id)
    benchmarks, benchmark_source, benchmark_location = get_or_refresh_benchmarks(db, household, income_for_benchmark)
    account_outs = [
        AccountOut(id=a.id, name=a.name, institution=a.institution, currency=a.currency, account_type=a.account_type, source=a.source, is_active=a.is_active, latest_balance=balances.get(a.id, 0.0))
        for a in accounts
    ]
    wealth_series_data = month_rows_wealth_series_adjusted(month_rows, invest_rows, year, month, 12)
    selected_row = month_row_lookup(month_rows, year, month)
    selected_invest = investment_row_lookup(invest_rows, year, month)
    selected_nw = 0.0
    if selected_row is not None:
        cum = selected_invest.cum_invest if selected_invest is not None else 0.0
        real = selected_invest.real_value if selected_invest is not None else None
        selected_nw = adjusted_net_worth(selected_row.net_worth, cum, real)

    return DashboardOut(
        net_worth=selected_nw,
        month=build_monthly_summary(db, household_id, year, month, txs, strategy, month_rows),
        spend_by_category=spend_by_category(txs, benchmarks),
        accounts=account_outs,
        invested_total=invested_total,
        strategy=strategy_out(strategy),
        month_rows=month_rows,
        investment_month_rows=invest_rows,
        yearly_objectives=yearly_objectives,
        wealth_series=wealth_series_data,
        wealth_projection=projection,
        wealth_projection_no_invest=projection_no_invest,
        projection_assumptions=assumptions,
        benchmark_location=benchmark_location,
        benchmark_source=benchmark_source,
    )
