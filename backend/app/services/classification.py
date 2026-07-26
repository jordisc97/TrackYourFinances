import re

from sqlalchemy.orm import Session, joinedload

from app.models import Category, CategoryRule, Transaction
from app.services.deepseek import LLM_RULE_PRIORITY, classify_with_deepseek


def match_category(db: Session, household_id: int, description: str, merchant: str) -> int | None:
    haystack = f"{description} {merchant}".lower()
    rules = (
        db.query(CategoryRule)
        .join(Category)
        .options(joinedload(CategoryRule.category))
        .filter(Category.household_id == household_id, CategoryRule.is_active.is_(True))
        .order_by(CategoryRule.priority.asc())
        .all()
    )
    for rule in rules:
        pattern = rule.pattern.lower()
        if rule.match_type == "regex" and re.search(rule.pattern, haystack, re.IGNORECASE):
            return rule.category_id
        if rule.match_type == "contains" and pattern in haystack:
            return rule.category_id
        if rule.match_type == "exact" and pattern == haystack.strip():
            return rule.category_id
    return None


def _persist_llm_rule(db: Session, category_id: int, merchant: str, description: str) -> None:
    pattern = (merchant or description or "").strip()[:255]
    if not pattern:
        return
    exists = db.query(CategoryRule).filter(CategoryRule.category_id == category_id, CategoryRule.pattern == pattern, CategoryRule.match_type == "contains").first()
    if exists is not None:
        return
    db.add(CategoryRule(category_id=category_id, pattern=pattern, match_type="contains", priority=LLM_RULE_PRIORITY))


def classify_transaction(db: Session, household_id: int, tx: Transaction) -> Transaction:
    if tx.category_id is not None:
        return tx
    category_id = match_category(db, household_id, tx.raw_description, tx.merchant)
    if category_id is not None:
        tx.category_id = category_id
        return tx
    category_name = classify_with_deepseek(tx.raw_description, tx.merchant, tx.amount, tx.currency)
    if category_name is None:
        return tx
    category = db.query(Category).filter(Category.household_id == household_id, Category.name == category_name).first()
    if category is None:
        return tx
    tx.category_id = category.id
    _persist_llm_rule(db, category.id, tx.merchant, tx.raw_description)
    return tx


def classify_uncategorized(db: Session, household_id: int, account_ids: list[int]) -> int:
    txs = db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).all()
    updated = 0
    for tx in txs:
        before = tx.category_id
        classify_transaction(db, household_id, tx)
        if tx.category_id != before:
            updated += 1
    db.commit()
    return updated
