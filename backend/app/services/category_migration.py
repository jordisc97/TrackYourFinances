from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Category, CategoryRule, Household, Transaction
from app.seed import DEFAULT_CATEGORIES, ensure_default_category_rules

OBSOLETE_CATEGORY_NAMES = ("Food", "Transport", "Leisure", "Other")
CATEGORY_RENAMES = {"Transport": "Transportation", "Leisure": "Entertainment & Leisure"}
CLEAR_CATEGORY_NAMES = ("Food", "Other")


def _ensure_default_categories(db: Session, household_id: int) -> dict[str, Category]:
    by_name = {c.name: c for c in db.query(Category).filter(Category.household_id == household_id).all()}
    for name, kind, color in DEFAULT_CATEGORIES:
        if name in by_name:
            continue
        category = Category(household_id=household_id, name=name, kind=kind, color=color, is_system=True)
        db.add(category)
        db.flush()
        by_name[name] = category
    return by_name


def _remap_category_refs(db: Session, old_id: int, new_id: int) -> None:
    db.query(Transaction).filter(Transaction.category_id == old_id).update({Transaction.category_id: new_id}, synchronize_session=False)
    db.query(CategoryRule).filter(CategoryRule.category_id == old_id).update({CategoryRule.category_id: new_id}, synchronize_session=False)


def _clear_category_refs(db: Session, category_id: int) -> None:
    db.query(Transaction).filter(Transaction.category_id == category_id).update({Transaction.category_id: None}, synchronize_session=False)
    db.query(CategoryRule).filter(CategoryRule.category_id == category_id).delete(synchronize_session=False)


def migrate_household_categories(db: Session, household_id: int) -> None:
    by_name = _ensure_default_categories(db, household_id)
    for old_name, new_name in CATEGORY_RENAMES.items():
        old_cat = by_name.get(old_name)
        new_cat = by_name.get(new_name)
        if old_cat is None or new_cat is None or old_cat.id == new_cat.id:
            continue
        _remap_category_refs(db, old_cat.id, new_cat.id)
    for clear_name in CLEAR_CATEGORY_NAMES:
        clear_cat = by_name.get(clear_name)
        if clear_cat is None:
            continue
        _clear_category_refs(db, clear_cat.id)
    for obsolete_name in OBSOLETE_CATEGORY_NAMES:
        obsolete = by_name.get(obsolete_name)
        if obsolete is None:
            continue
        db.delete(obsolete)
    ensure_default_category_rules(db, household_id)


def household_needs_category_migration(db: Session, household_id: int) -> bool:
    names = {c.name for c in db.query(Category).filter(Category.household_id == household_id).all()}
    if names.intersection(OBSOLETE_CATEGORY_NAMES):
        return True
    expected = {name for name, _, _ in DEFAULT_CATEGORIES}
    return not expected.issubset(names)


def migrate_all_household_categories() -> None:
    db = SessionLocal()
    households = db.query(Household).all()
    for household in households:
        if not household_needs_category_migration(db, household.id):
            ensure_default_category_rules(db, household.id)
            continue
        migrate_household_categories(db, household.id)
    db.commit()
    db.close()
