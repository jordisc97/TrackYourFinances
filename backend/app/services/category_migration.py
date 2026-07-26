from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Category, Household
from app.seed import DEFAULT_CATEGORIES, ensure_default_category_rules


def ensure_default_categories(db: Session, household_id: int) -> None:
    by_name = {c.name: c for c in db.query(Category).filter(Category.household_id == household_id).all()}
    for name, kind, color in DEFAULT_CATEGORIES:
        if name in by_name:
            continue
        db.add(Category(household_id=household_id, name=name, kind=kind, color=color, is_system=True))
    db.flush()
    ensure_default_category_rules(db, household_id)


def ensure_all_household_defaults() -> None:
    db = SessionLocal()
    for household in db.query(Household).all():
        ensure_default_categories(db, household.id)
    db.commit()
    db.close()
