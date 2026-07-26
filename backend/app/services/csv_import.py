import csv
import io
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Account, Transaction, TransactionSource
from app.services.classification import match_category
from app.services.csv_mapping import SAMPLE_ROW_LIMIT, pick_mapped, resolve_column_mapping

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
MISSING_MAPPING_MESSAGE = "Could not map CSV columns to booked_at and amount. Check headers or configure DEEPSEEK_API."


class CsvMappingError(ValueError):
    pass


def parse_date(value: str) -> date:
    cleaned = value.strip()[:10] if "T" in value else value.strip()
    for fmt in DATE_FORMATS:
        parsed = _safe_strptime(cleaned, fmt)
        if parsed is not None:
            return parsed
    raise ValueError(f"Unrecognized date: {value}")


def _safe_strptime(value: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(value, fmt).date()
    except ValueError:
        return None


def parse_amount(value: str) -> float:
    cleaned = value.strip().replace("€", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".") if cleaned.rfind(",") > cleaned.rfind(".") else cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def import_transactions_csv(db: Session, account: Account, content: str) -> tuple[int, int]:
    reader = csv.DictReader(io.StringIO(content))
    headers = list(reader.fieldnames or [])
    rows = [{key: (value or "") for key, value in row.items() if key is not None} for row in reader]
    mapping = resolve_column_mapping(headers, rows[:SAMPLE_ROW_LIMIT])
    missing = mapping.missing_required()
    if missing:
        raise CsvMappingError(f"{MISSING_MAPPING_MESSAGE} Missing: {', '.join(missing)}")
    imported, skipped = 0, 0
    for row in rows:
        date_raw = pick_mapped(row, mapping, "booked_at")
        amount_raw = pick_mapped(row, mapping, "amount")
        if not date_raw or not amount_raw:
            skipped += 1
            continue
        booked_at = parse_date(date_raw)
        amount = parse_amount(amount_raw)
        description = pick_mapped(row, mapping, "raw_description")
        merchant = pick_mapped(row, mapping, "merchant")
        external_id = pick_mapped(row, mapping, "external_id") or f"csv-{uuid4().hex}"
        existing = db.query(Transaction).filter(Transaction.account_id == account.id, Transaction.external_id == external_id).first()
        if existing:
            skipped += 1
            continue
        tx = Transaction(account_id=account.id, booked_at=booked_at, amount=amount, currency=account.currency, raw_description=description, merchant=merchant or description, external_id=external_id, source=TransactionSource.csv.value)
        tx.category_id = match_category(db, account.household_id, description, merchant or description)
        db.add(tx)
        imported += 1
    db.commit()
    return imported, skipped
