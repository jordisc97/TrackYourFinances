"""One-shot: classify all uncategorized transactions (rules first, then DeepSeek batched by merchant/description)."""
from collections import defaultdict

from app.database import SessionLocal
from app.models import Account, Category, CategoryRule, Household, Transaction
from app.services.classification import match_category
from app.services.deepseek import LLM_RULE_PRIORITY, classify_with_deepseek


def _batch_key(tx: Transaction) -> str:
    merchant = (tx.merchant or "").strip()
    if merchant:
        return merchant.lower()
    return (tx.raw_description or "").strip().lower()[:255]


def _persist_rule(db, category_id: int, pattern: str) -> None:
    pattern = pattern.strip()[:255]
    if not pattern:
        return
    exists = (
        db.query(CategoryRule)
        .filter(CategoryRule.category_id == category_id, CategoryRule.pattern == pattern, CategoryRule.match_type == "contains")
        .first()
    )
    if exists is not None:
        return
    db.add(CategoryRule(category_id=category_id, pattern=pattern, match_type="contains", priority=LLM_RULE_PRIORITY))


def classify_household(db, household_id: int, account_ids: list[int]) -> tuple[int, int, int]:
    txs = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None))
        .all()
    )
    rule_hits = 0
    remaining: list[Transaction] = []
    for tx in txs:
        category_id = match_category(db, household_id, tx.raw_description, tx.merchant)
        if category_id is not None:
            tx.category_id = category_id
            rule_hits += 1
        else:
            remaining.append(tx)
    db.commit()

    groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in remaining:
        groups[_batch_key(tx)].append(tx)

    llm_hits = 0
    still_open = 0
    categories = {c.name: c for c in db.query(Category).filter(Category.household_id == household_id).all()}
    for idx, (key, group) in enumerate(groups.items(), start=1):
        sample = group[0]
        print(f"  llm {idx}/{len(groups)} key={key[:60]!r} n={len(group)}")
        name = classify_with_deepseek(sample.raw_description, sample.merchant, sample.amount, sample.currency)
        category = categories.get(name) if name else None
        if category is None:
            still_open += len(group)
            continue
        pattern = (sample.merchant or sample.raw_description or "").strip()
        for tx in group:
            tx.category_id = category.id
            llm_hits += 1
        _persist_rule(db, category.id, pattern)
        db.commit()
    return rule_hits, llm_hits, still_open


def main() -> None:
    db = SessionLocal()
    total_rules = total_llm = total_open = 0
    for household in db.query(Household).all():
        account_ids = [a.id for a in db.query(Account).filter(Account.household_id == household.id).all()]
        if not account_ids:
            continue
        before = db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).count()
        print(f"household {household.id}: {before} uncategorized")
        rule_hits, llm_hits, still_open = classify_household(db, household.id, account_ids)
        print(f"  rules={rule_hits} llm={llm_hits} left={still_open}")
        total_rules += rule_hits
        total_llm += llm_hits
        total_open += still_open
    left = db.query(Transaction).filter(Transaction.category_id.is_(None)).count()
    print(f"done rules={total_rules} llm={total_llm} still_open={total_open} db_uncategorized={left}")
    if left:
        samples = db.query(Transaction).filter(Transaction.category_id.is_(None)).limit(20).all()
        for tx in samples:
            print(f"  leftover {tx.id}: merchant={tx.merchant!r} desc={tx.raw_description[:80]!r}")
    db.close()


if __name__ == "__main__":
    main()
