import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Household, SpendBenchmark
from app.seed import EXPENSE_CATEGORY_NAMES

# Eurostat COICOP-style shares of consumption (EU ~2024), remapped to app categories.
# Applied to a typical spend budget (~70% of net income) so amounts scale with salary.
FALLBACK_CATEGORY_SHARES = {
    "Housing": 0.236,
    "Utilities": 0.055,
    "Groceries": 0.100,
    "Dining & Takeaway": 0.060,
    "Transportation": 0.127,
    "Health": 0.040,
    "Personal Care": 0.020,
    "Clothing & Footwear": 0.040,
    "Electronics & Home Goods": 0.045,
    "Subscriptions": 0.020,
    "Entertainment & Leisure": 0.055,
    "Travel": 0.035,
    "Childcare/Education": 0.015,
    "Pets": 0.010,
    "Gifts & Donations": 0.015,
    "Bank & Financial Fees": 0.010,
    "One-off Large Purchases": 0.027,
}
TYPICAL_SPEND_OF_INCOME = 0.70
INCOME_CACHE_BUCKET = 100.0
DEFAULT_LOCATION = "European Union"


def round_income_for_cache(monthly_income: float) -> float:
    if monthly_income <= 0:
        return 0.0
    return round(monthly_income / INCOME_CACHE_BUCKET) * INCOME_CACHE_BUCKET


def fallback_benchmarks(monthly_income: float) -> dict[str, float]:
    budget = max(monthly_income, 0.0) * TYPICAL_SPEND_OF_INCOME
    return {name: round(budget * share, 2) for name, share in FALLBACK_CATEGORY_SHARES.items()}


def resolve_location(household: Household) -> str:
    text = (household.location or "").strip()
    return text if text else DEFAULT_LOCATION


def _parse_cached(row: SpendBenchmark | None) -> dict[str, float]:
    if row is None or not row.benchmarks_json:
        return {}
    raw = json.loads(row.benchmarks_json)
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items() if k in EXPENSE_CATEGORY_NAMES}


def _persist_benchmarks(db: Session, household: Household, location: str, income_key: float, amounts: dict[str, float], source: str) -> SpendBenchmark:
    cached = household.spend_benchmark
    if cached is None:
        cached = SpendBenchmark(household_id=household.id)
        db.add(cached)
        household.spend_benchmark = cached
    cached.location = location
    cached.monthly_income = income_key
    cached.benchmarks_json = json.dumps(amounts)
    cached.source = source
    cached.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cached)
    return cached


def get_or_refresh_benchmarks(db: Session, household: Household, monthly_income: float) -> tuple[dict[str, float], str, str]:
    # Dashboard must stay instant: never call DeepSeek on this path.
    location = resolve_location(household)
    income_key = round_income_for_cache(monthly_income)
    cached = household.spend_benchmark
    if cached is not None and cached.location == location and cached.benchmarks_json:
        amounts = _parse_cached(cached)
        if amounts and cached.monthly_income > 0 and income_key > 0 and abs(cached.monthly_income - income_key) >= 0.01:
            scale = income_key / cached.monthly_income
            amounts = {name: round(value * scale, 2) for name, value in amounts.items()}
            return amounts, cached.source, location
        if amounts:
            return amounts, cached.source, location
    amounts = fallback_benchmarks(monthly_income)
    _persist_benchmarks(db, household, location, income_key, amounts, "eurostat_fallback")
    return amounts, "eurostat_fallback", location


def invalidate_benchmarks(db: Session, household_id: int) -> None:
    row = db.query(SpendBenchmark).filter(SpendBenchmark.household_id == household_id).first()
    if row is None:
        return
    db.delete(row)
    db.commit()
