import csv
import io

from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot
from app.services.csv_import import CsvMappingError, parse_amount, parse_date
from app.services.sync import upsert_balance

DATE_COLUMN = "date"
VALUE_COLUMN = "account_value_eur"
MISSING_COLUMNS_MESSAGE = "Investment CSV requires date and account_value_eur columns."


def import_investment_balances_csv(db: Session, account: Account, content: str, overwrite: bool = False) -> tuple[int, int, int]:
    reader = csv.DictReader(io.StringIO(content))
    headers = {(header or "").strip() for header in (reader.fieldnames or [])}
    if DATE_COLUMN not in headers or VALUE_COLUMN not in headers:
        raise CsvMappingError(MISSING_COLUMNS_MESSAGE)
    replaced = 0
    if overwrite:
        replaced = int(db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account.id).delete(synchronize_session=False) or 0)
    imported, skipped = 0, 0
    for row in reader:
        date_raw = (row.get(DATE_COLUMN) or "").strip()
        amount_raw = (row.get(VALUE_COLUMN) or "").strip()
        if not date_raw or not amount_raw:
            skipped += 1
            continue
        upsert_balance(db, account, parse_amount(amount_raw), parse_date(date_raw))
        imported += 1
    db.commit()
    return imported, skipped, replaced
