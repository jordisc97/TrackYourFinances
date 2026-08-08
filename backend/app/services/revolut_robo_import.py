import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models import Account, AccountType, Category, InvestmentHolding, Transaction, TransactionSource
from app.services.csv_import import CsvMappingError, parse_date

COL_DATE = "Date"
COL_TICKER = "Ticker"
COL_TYPE = "Type"
COL_QUANTITY = "Quantity"
COL_PRICE = "Price per share"
COL_TOTAL = "Total Amount"
COL_CURRENCY = "Currency"
COL_FX = "FX Rate"
REQUIRED_HEADERS = (COL_DATE, COL_TICKER, COL_TYPE, COL_QUANTITY, COL_PRICE, COL_TOTAL, COL_CURRENCY, COL_FX)
FORMAT_NAME = "Revolut Robo-Advisor"
MISSING_HEADERS_MESSAGE = "File is not a Revolut Robo-Advisor CSV. Required columns: Date, Ticker, Type, Quantity, Price per share, Total Amount, Currency, FX Rate."

ACTIVITY_CASH_TOP_UP = "cash_top_up"
ACTIVITY_BUY = "buy_market"
ACTIVITY_SELL = "sell_market"
ACTIVITY_DIVIDEND = "dividend"
ACTIVITY_FEE = "management_fee"
ACTIVITY_UNKNOWN = "unknown"

TYPE_CASH_TOP_UP = "CASH TOP-UP"
TYPE_BUY_MARKET = "BUY - MARKET"
TYPE_SELL_MARKET = "SELL - MARKET"
TYPE_DIVIDEND = "DIVIDEND"
TYPE_ROBO_FEE = "ROBO MANAGEMENT FEE"

TYPE_TO_ACTIVITY = {
    TYPE_CASH_TOP_UP: ACTIVITY_CASH_TOP_UP,
    TYPE_BUY_MARKET: ACTIVITY_BUY,
    TYPE_SELL_MARKET: ACTIVITY_SELL,
    TYPE_DIVIDEND: ACTIVITY_DIVIDEND,
    TYPE_ROBO_FEE: ACTIVITY_FEE,
}

CATEGORY_BY_ACTIVITY = {
    ACTIVITY_CASH_TOP_UP: "Investment",
    ACTIVITY_BUY: "Investment",
    ACTIVITY_SELL: "Investment",
    ACTIVITY_DIVIDEND: "Dividend",
    ACTIVITY_FEE: "Management Fee",
    ACTIVITY_UNKNOWN: "Investment",
}

MONEY_PREFIX_RE = re.compile(r"^([A-Za-z]{3})\s+(-?\d+(?:[.,]\d+)?)$")
MATCH_WINDOW_DAYS = 3
REVOLUT_HINT = "revolut"


@dataclass
class ParsedMoney:
    amount: float
    currency: str


@dataclass
class ParsedRevolutRow:
    booked_at: date
    timestamp_raw: str
    ticker: str
    raw_type: str
    activity: str
    quantity: float | None
    price_per_share: float | None
    total_amount: float
    currency: str
    fx_rate: float | None
    balance_amount: float
    trade_total: float


@dataclass
class RevolutImportSummary:
    account_type: str = "investment"
    format_detected: str = FORMAT_NAME
    transactions: int = 0
    contributions: float = 0.0
    purchases: float = 0.0
    dividends: float = 0.0
    management_fees: float = 0.0
    securities: int = 0
    currency: str = "EUR"
    unknown_types: list[str] = field(default_factory=list)


def detect_revolut_robo_headers(headers: list[str]) -> bool:
    normalized = {(header or "").strip() for header in headers}
    return all(name in normalized for name in REQUIRED_HEADERS)


def parse_money_field(value: str) -> ParsedMoney:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Empty money field")
    match = MONEY_PREFIX_RE.match(cleaned)
    if match:
        currency, amount_raw = match.group(1).upper(), match.group(2).replace(",", ".")
        return ParsedMoney(amount=float(amount_raw), currency=currency)
    amount_raw = cleaned.replace("€", "").replace(",", ".").strip()
    return ParsedMoney(amount=float(amount_raw), currency="")


def parse_optional_float(value: str) -> float | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    money = parse_money_field(cleaned) if any(ch.isalpha() for ch in cleaned) else None
    if money is not None:
        return money.amount
    return float(cleaned.replace(",", "."))


def parse_optional_quantity(value: str) -> float | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return float(cleaned.replace(",", "."))


def _balance_amount_for_activity(activity: str, total_amount: float) -> float:
    if activity in (ACTIVITY_BUY, ACTIVITY_SELL):
        return 0.0
    return total_amount


def parse_revolut_row(row: dict[str, str]) -> ParsedRevolutRow:
    timestamp_raw = (row.get(COL_DATE) or "").strip()
    booked_at = parse_date(timestamp_raw)
    ticker = (row.get(COL_TICKER) or "").strip()
    raw_type = (row.get(COL_TYPE) or "").strip()
    activity = TYPE_TO_ACTIVITY.get(raw_type, ACTIVITY_UNKNOWN)
    quantity = parse_optional_quantity(row.get(COL_QUANTITY) or "")
    price_raw = (row.get(COL_PRICE) or "").strip()
    price_per_share = parse_optional_float(price_raw) if price_raw else None
    total = parse_money_field(row.get(COL_TOTAL) or "")
    currency = ((row.get(COL_CURRENCY) or "").strip().upper() or total.currency or "EUR")
    fx_raw = (row.get(COL_FX) or "").strip()
    fx_rate = float(fx_raw.replace(",", ".")) if fx_raw else None
    return ParsedRevolutRow(
        booked_at=booked_at,
        timestamp_raw=timestamp_raw,
        ticker=ticker,
        raw_type=raw_type,
        activity=activity,
        quantity=quantity,
        price_per_share=price_per_share,
        total_amount=total.amount,
        currency=currency,
        fx_rate=fx_rate,
        balance_amount=_balance_amount_for_activity(activity, total.amount),
        trade_total=abs(total.amount) if activity in (ACTIVITY_BUY, ACTIVITY_SELL) else 0.0,
    )


def parse_revolut_csv_bytes(content_bytes: bytes) -> tuple[list[str], list[dict[str, str]]]:
    content = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    headers = list(reader.fieldnames or [])
    if not detect_revolut_robo_headers(headers):
        raise CsvMappingError(MISSING_HEADERS_MESSAGE)
    rows = [{key: (value or "") for key, value in row.items() if key is not None} for row in reader]
    return headers, rows


def build_revolut_summary(parsed_rows: list[ParsedRevolutRow]) -> RevolutImportSummary:
    unknown = sorted({row.raw_type for row in parsed_rows if row.activity == ACTIVITY_UNKNOWN and row.raw_type})
    tickers = {row.ticker for row in parsed_rows if row.ticker}
    currencies = [row.currency for row in parsed_rows if row.currency]
    currency = currencies[0] if currencies else "EUR"
    contributions = round(sum(row.total_amount for row in parsed_rows if row.activity == ACTIVITY_CASH_TOP_UP), 2)
    purchases = round(sum(row.trade_total for row in parsed_rows if row.activity == ACTIVITY_BUY), 2)
    dividends = round(sum(row.total_amount for row in parsed_rows if row.activity == ACTIVITY_DIVIDEND), 2)
    fees = round(sum(row.total_amount for row in parsed_rows if row.activity == ACTIVITY_FEE), 2)
    return RevolutImportSummary(
        transactions=len(parsed_rows),
        contributions=contributions,
        purchases=purchases,
        dividends=dividends,
        management_fees=fees,
        securities=len(tickers),
        currency=currency,
        unknown_types=unknown,
    )


def preview_revolut_robo_csv(content_bytes: bytes) -> RevolutImportSummary:
    _, rows = parse_revolut_csv_bytes(content_bytes)
    parsed = [parse_revolut_row(row) for row in rows if (row.get(COL_DATE) or "").strip() and (row.get(COL_TYPE) or "").strip()]
    return build_revolut_summary(parsed)


def _stable_revolut_external_id(account_id: int, row: ParsedRevolutRow, seen_keys: dict[str, int]) -> str:
    qty = "" if row.quantity is None else f"{row.quantity}"
    fingerprint = "|".join([row.timestamp_raw, row.ticker, row.raw_type, qty, f"{row.total_amount}", row.currency])
    digest = hashlib.sha256(f"{account_id}:{fingerprint}".encode()).hexdigest()[:32]
    base = f"revolut-{digest}"
    duplicate_count = seen_keys.get(base, 0)
    seen_keys[base] = duplicate_count + 1
    return base if duplicate_count == 0 else f"{base}-dup{duplicate_count}"


def _category_map(db: Session, household_id: int) -> dict[str, Category]:
    return {c.name: c for c in db.query(Category).filter(Category.household_id == household_id).all()}


def _apply_holding_delta(db: Session, account_id: int, ticker: str, quantity_delta: float) -> None:
    if not ticker or quantity_delta == 0:
        return
    for pending in db.new:
        if isinstance(pending, InvestmentHolding) and pending.account_id == account_id and pending.ticker == ticker:
            pending.quantity = round(pending.quantity + quantity_delta, 8)
            return
    holding = db.query(InvestmentHolding).filter(InvestmentHolding.account_id == account_id, InvestmentHolding.ticker == ticker).first()
    if holding is None:
        db.add(InvestmentHolding(account_id=account_id, ticker=ticker, quantity=quantity_delta))
        return
    holding.quantity = round(holding.quantity + quantity_delta, 8)


def _rebuild_holdings_from_rows(db: Session, account_id: int, parsed_rows: list[ParsedRevolutRow]) -> None:
    db.query(InvestmentHolding).filter(InvestmentHolding.account_id == account_id).delete(synchronize_session=False)
    totals: dict[str, float] = {}
    for row in parsed_rows:
        if not row.ticker or row.quantity is None:
            continue
        if row.activity == ACTIVITY_BUY:
            totals[row.ticker] = round(totals.get(row.ticker, 0.0) + row.quantity, 8)
        elif row.activity == ACTIVITY_SELL:
            totals[row.ticker] = round(totals.get(row.ticker, 0.0) - row.quantity, 8)
    for ticker, quantity in totals.items():
        db.add(InvestmentHolding(account_id=account_id, ticker=ticker, quantity=quantity))


def _match_checking_outflow(db: Session, household_id: int, invest_account: Account, top_up: ParsedRevolutRow, used_ids: set[int]) -> Transaction | None:
    source_types = (AccountType.checking.value, AccountType.savings.value)
    accounts = db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True), Account.account_type.in_(source_types)).all()
    if not accounts:
        return None
    account_ids = [a.id for a in accounts]
    window_start = top_up.booked_at - timedelta(days=MATCH_WINDOW_DAYS)
    window_end = top_up.booked_at + timedelta(days=MATCH_WINDOW_DAYS)
    target = abs(top_up.total_amount)
    candidates = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .filter(Transaction.account_id.in_(account_ids), Transaction.booked_at >= window_start, Transaction.booked_at <= window_end, Transaction.amount < 0)
        .all()
    )
    invest_name = (invest_account.name or "").strip().lower()
    best: Transaction | None = None
    best_score = -1
    for tx in candidates:
        if tx.id in used_ids:
            continue
        if round(abs(tx.amount), 2) != round(target, 2):
            continue
        haystack = f"{tx.raw_description} {tx.merchant}".lower()
        has_hint = (invest_name and invest_name in haystack) or REVOLUT_HINT in haystack
        if not has_hint:
            continue
        score = 2
        if invest_name and invest_name in haystack:
            score += 2
        if REVOLUT_HINT in haystack:
            score += 2
        day_gap = abs((tx.booked_at - top_up.booked_at).days)
        score += max(0, MATCH_WINDOW_DAYS - day_gap)
        if score > best_score:
            best, best_score = tx, score
    return best


def _reclassify_matched_transfers(db: Session, household_id: int, invest_account: Account, top_ups: list[ParsedRevolutRow]) -> int:
    transfer = db.query(Category).filter(Category.household_id == household_id, Category.name == "Transfer").first()
    if transfer is None:
        return 0
    used_ids: set[int] = set()
    updated = 0
    for top_up in top_ups:
        matched = _match_checking_outflow(db, household_id, invest_account, top_up, used_ids)
        if matched is None:
            continue
        used_ids.add(matched.id)
        matched.category_id = transfer.id
        matched.merchant = matched.merchant or invest_account.name
        matched.raw_description = matched.raw_description or invest_account.name
        if invest_account.name and invest_account.name.lower() not in f"{matched.raw_description} {matched.merchant}".lower():
            matched.raw_description = f"{matched.raw_description} {invest_account.name}".strip()
        updated += 1
    return updated


def import_revolut_robo_csv(db: Session, account: Account, content_bytes: bytes, overwrite: bool = False) -> tuple[int, int, int, int, RevolutImportSummary]:
    if account.account_type != AccountType.investment.value:
        raise CsvMappingError("Revolut Robo-Advisor import requires an investment account")
    _, rows = parse_revolut_csv_bytes(content_bytes)
    parsed_rows = [parse_revolut_row(row) for row in rows if (row.get(COL_DATE) or "").strip() and (row.get(COL_TYPE) or "").strip()]
    summary = build_revolut_summary(parsed_rows)
    categories = _category_map(db, account.household_id)
    replaced = 0
    if overwrite:
        replaced = int(db.query(Transaction).filter(Transaction.account_id == account.id).delete(synchronize_session=False) or 0)
        db.query(InvestmentHolding).filter(InvestmentHolding.account_id == account.id).delete(synchronize_session=False)
        db.commit()
    existing_ids: set[str] = set()
    if not overwrite:
        existing_ids = {row[0] for row in db.query(Transaction.external_id).filter(Transaction.account_id == account.id, Transaction.external_id.isnot(None)).all() if row[0]}
    seen_keys: dict[str, int] = {}
    imported, skipped, categorized = 0, 0, 0
    newly_parsed: list[ParsedRevolutRow] = []
    for row in parsed_rows:
        external_id = _stable_revolut_external_id(account.id, row, seen_keys)
        if not overwrite and external_id in existing_ids:
            skipped += 1
            continue
        category_name = CATEGORY_BY_ACTIVITY.get(row.activity, "Investment")
        category = categories.get(category_name) or categories.get("Investment")
        description = f"{row.raw_type}" + (f" {row.ticker}" if row.ticker else "")
        tx = Transaction(
            account_id=account.id,
            category_id=category.id if category else None,
            booked_at=row.booked_at,
            amount=row.balance_amount,
            currency=row.currency,
            raw_description=f"{description} @ {row.timestamp_raw}",
            merchant=row.ticker or row.raw_type,
            external_id=external_id,
            source=TransactionSource.csv.value,
            investment_activity=row.activity,
            ticker=row.ticker or None,
            quantity=row.quantity,
            price_per_share=row.price_per_share,
            fx_rate=row.fx_rate,
        )
        if tx.category_id is not None:
            categorized += 1
        db.add(tx)
        existing_ids.add(external_id)
        newly_parsed.append(row)
        imported += 1
        if not overwrite and row.activity == ACTIVITY_BUY and row.ticker and row.quantity is not None:
            _apply_holding_delta(db, account.id, row.ticker, row.quantity)
        elif not overwrite and row.activity == ACTIVITY_SELL and row.ticker and row.quantity is not None:
            _apply_holding_delta(db, account.id, row.ticker, -row.quantity)
    if overwrite:
        _rebuild_holdings_from_rows(db, account.id, parsed_rows)
    top_ups = [row for row in newly_parsed if row.activity == ACTIVITY_CASH_TOP_UP]
    _reclassify_matched_transfers(db, account.household_id, account, top_ups)
    db.commit()
    return imported, skipped, replaced, categorized, summary
