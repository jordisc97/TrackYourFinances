import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Account, Household, Transaction
from app.services.classification import classify_uncategorized

logger = logging.getLogger(__name__)


def categorize_all_households(db: Session | None = None) -> int:
    settings = get_settings()
    owns_session = db is None
    session = db or SessionLocal()
    use_llm = bool(settings.deepseek_api)
    total = 0
    households = session.query(Household.id).all()
    for (household_id,) in households:
        account_ids = [row[0] for row in session.query(Account.id).filter(Account.household_id == household_id).all()]
        if not account_ids:
            continue
        pending = session.query(Transaction.id).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).limit(1).first()
        if pending is None:
            continue
        total += classify_uncategorized(session, household_id, account_ids, use_llm=use_llm)
    if owns_session:
        session.close()
    if total:
        logger.info("Periodic categorize assigned %s transactions", total)
    return total
