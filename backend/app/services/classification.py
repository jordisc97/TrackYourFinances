import re
import time
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models import Account, Category, CategoryRule, KnownCommerce, Transaction
from app.services.accounts_helpers import match_own_account_id
from app.services.deepseek import LLM_RULE_PRIORITY, classify_batch_with_deepseek, classify_with_deepseek

LLM_BATCH_SIZE = 25
EMPLOYER_RULE_PRIORITY = 5
MANUAL_RULE_PRIORITY = 50
MIN_MERCHANT_STEM_LEN = 3
INCOME_CATEGORY_NAME = "Income"
TRANSFER_CATEGORY_NAME = "Transfer"
INCOME_KIND = "income"
EXPENSE_KIND = "expense"
MERCHANT_TRAILING_NOISE = frozenset({
    "stores", "store", "limited", "ltd", "inc", "llc", "gmbh", "sa", "sl", "plc", "co", "company",
    "pending", "webuy", "ireland", "dublin", "ie",
})
MERCHANT_PREFIX_NOISE = frozenset({"sq", "paypal", "sumup", "zettle", "stripe", "clr"})
AMBIGUOUS_BRAND_PREFIXES = frozenset({"uber", "amazon", "apple", "google"})
MERCHANT_KEEP_CHARS_RE = re.compile(r"[^\w\sÀ-ÿ&'-]", re.UNICODE)
MERCHANT_DIGITS_RE = re.compile(r"\b\d+\b")
MERCHANT_STARS_RE = re.compile(r"[*]+")
MERCHANT_SPACES_RE = re.compile(r"\s+")


def load_household_accounts(db: Session, household_id: int) -> list[Account]:
    return db.query(Account).filter(Account.household_id == household_id, Account.is_active.is_(True)).all()


def match_own_account_transfer(db: Session, household_id: int, description: str, merchant: str, exclude_account_id: int | None = None, accounts: list[Account] | None = None) -> int | None:
    active = accounts if accounts is not None else load_household_accounts(db, household_id)
    if match_own_account_id(active, description, merchant, exclude_account_id) is None:
        return None
    transfer = db.query(Category).filter(Category.household_id == household_id, Category.name == TRANSFER_CATEGORY_NAME).first()
    return transfer.id if transfer is not None else None


def load_category_rules(db: Session, household_id: int) -> list[CategoryRule]:
    return (
        db.query(CategoryRule)
        .join(Category)
        .options(joinedload(CategoryRule.category))
        .filter(Category.household_id == household_id, CategoryRule.is_active.is_(True))
        .order_by(CategoryRule.priority.asc())
        .all()
    )


def _rule_applies_to_amount(rule: CategoryRule, amount: float | None) -> bool:
    if amount is None or rule.category is None:
        return True
    kind = rule.category.kind
    if kind == INCOME_KIND and amount <= 0:
        return False
    if kind == EXPENSE_KIND and amount > 0:
        return False
    return True


def _match_haystack(description: str, merchant: str) -> str:
    text = f"{description} {merchant}".lower()
    text = MERCHANT_STARS_RE.sub(" ", text)
    return MERCHANT_SPACES_RE.sub(" ", text).strip()


def match_category_with_rules(rules: list[CategoryRule], description: str, merchant: str, amount: float | None = None) -> int | None:
    haystack = _match_haystack(description, merchant)
    for rule in rules:
        if not _rule_applies_to_amount(rule, amount):
            continue
        pattern = rule.pattern.lower()
        if rule.match_type == "regex" and re.search(rule.pattern, haystack, re.IGNORECASE):
            return rule.category_id
        if rule.match_type == "contains" and pattern in haystack:
            return rule.category_id
        if rule.match_type == "exact" and pattern == haystack.strip():
            return rule.category_id
    return None


def match_category(db: Session, household_id: int, description: str, merchant: str, amount: float | None = None) -> int | None:
    return match_category_with_rules(load_category_rules(db, household_id), description, merchant, amount)


def merchant_match_pattern(merchant: str, description: str) -> str:
    raw = (merchant or description or "").strip()
    if not raw:
        return ""
    text = MERCHANT_STARS_RE.sub(" ", raw.lower())
    text = MERCHANT_KEEP_CHARS_RE.sub(" ", text)
    text = MERCHANT_DIGITS_RE.sub(" ", text)
    tokens = [token for token in text.split() if token]
    if tokens and tokens[0] in MERCHANT_PREFIX_NOISE:
        tokens = tokens[1:]
    while tokens and tokens[-1] in MERCHANT_TRAILING_NOISE:
        tokens.pop()
    if not tokens:
        return MERCHANT_SPACES_RE.sub(" ", raw).strip()[:255]
    # Prefer brand stem; keep a second token for short or ambiguous prefixes (uber eats).
    if len(tokens) >= 2 and (len(tokens[0]) < MIN_MERCHANT_STEM_LEN + 1 or tokens[0] in AMBIGUOUS_BRAND_PREFIXES):
        stem = f"{tokens[0]} {tokens[1]}"
    else:
        stem = tokens[0]
    return stem[:255]


def _merchant_key(description: str, merchant: str) -> str:
    return merchant_match_pattern(merchant, description) or MERCHANT_SPACES_RE.sub(" ", (merchant or description or "").strip().lower())[:255]


def _category_by_name(db: Session, household_id: int) -> dict[str, Category]:
    return {category.name: category for category in db.query(Category).filter(Category.household_id == household_id).all()}


def load_known_commerces(db: Session) -> dict[str, str]:
    return {row.normalized_name: row.category_name for row in db.query(KnownCommerce).all()}


def remember_commerce(db: Session, merchant: str, description: str, category_name: str) -> None:
    key = _merchant_key(description, merchant)
    if not key or not category_name:
        return
    display = (merchant or description or "").strip()[:255]
    existing = db.query(KnownCommerce).filter(KnownCommerce.normalized_name == key).first()
    if existing is None:
        for pending in db.new:
            if isinstance(pending, KnownCommerce) and pending.normalized_name == key:
                existing = pending
                break
    if existing is not None:
        existing.category_name = category_name
        existing.display_name = display or existing.display_name
        existing.updated_at = datetime.utcnow()
        return
    db.add(KnownCommerce(normalized_name=key, display_name=display, category_name=category_name))


def match_known_commerce(db: Session, household_id: int, description: str, merchant: str, known: dict[str, str] | None = None, categories_by_name: dict[str, Category] | None = None) -> int | None:
    key = _merchant_key(description, merchant)
    if not key:
        return None
    commerce_map = known if known is not None else load_known_commerces(db)
    category_name = commerce_map.get(key)
    if category_name is None:
        return None
    by_name = categories_by_name if categories_by_name is not None else _category_by_name(db, household_id)
    category = by_name.get(category_name)
    return category.id if category is not None else None


def ensure_contains_rule(db: Session, category_id: int, pattern: str, priority: int = MANUAL_RULE_PRIORITY) -> CategoryRule | None:
    cleaned = MERCHANT_SPACES_RE.sub(" ", (pattern or "").strip())[:255]
    if len(cleaned) < MIN_MERCHANT_STEM_LEN:
        return None
    exists = db.query(CategoryRule).filter(CategoryRule.category_id == category_id, CategoryRule.pattern == cleaned, CategoryRule.match_type == "contains").first()
    if exists is not None:
        exists.is_active = True
        return exists
    for pending in db.new:
        if isinstance(pending, CategoryRule) and pending.category_id == category_id and pending.pattern == cleaned and pending.match_type == "contains":
            return pending
    rule = CategoryRule(category_id=category_id, pattern=cleaned, match_type="contains", priority=priority)
    db.add(rule)
    return rule


def apply_pattern_to_uncategorized(db: Session, account_ids: list[int], category_id: int, pattern: str) -> int:
    cleaned = MERCHANT_SPACES_RE.sub(" ", (pattern or "").strip().lower())
    if not cleaned or not account_ids:
        return 0
    updated = 0
    for tx in db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).all():
        if cleaned in _match_haystack(tx.raw_description, tx.merchant):
            tx.category_id = category_id
            updated += 1
    return updated


def _persist_llm_rule(db: Session, category_id: int, merchant: str, description: str) -> None:
    ensure_contains_rule(db, category_id, merchant_match_pattern(merchant, description) or (merchant or description or ""), LLM_RULE_PRIORITY)


def classify_transaction(db: Session, household_id: int, tx: Transaction, rules: list[CategoryRule] | None = None, use_llm: bool = True, accounts: list[Account] | None = None) -> Transaction:
    if tx.category_id is not None:
        return tx
    own_transfer_id = match_own_account_transfer(db, household_id, tx.raw_description, tx.merchant, tx.account_id, accounts)
    if own_transfer_id is not None:
        tx.category_id = own_transfer_id
        return tx
    active_rules = rules if rules is not None else load_category_rules(db, household_id)
    category_id = match_category_with_rules(active_rules, tx.raw_description, tx.merchant, tx.amount)
    if category_id is not None:
        tx.category_id = category_id
        return tx
    category_id = match_known_commerce(db, household_id, tx.raw_description, tx.merchant)
    if category_id is not None:
        tx.category_id = category_id
        return tx
    if not use_llm:
        return tx
    if tx.amount > 0:
        return tx
    category_name = classify_with_deepseek(tx.raw_description, tx.merchant, tx.amount, tx.currency)
    if category_name is None:
        return tx
    category = db.query(Category).filter(Category.household_id == household_id, Category.name == category_name).first()
    if category is None:
        return tx
    tx.category_id = category.id
    _persist_llm_rule(db, category.id, tx.merchant, tx.raw_description)
    remember_commerce(db, tx.merchant, tx.raw_description, category.name)
    return tx


def _assign_leftover_positives_as_transfer(db: Session, household_id: int, account_ids: list[int]) -> int:
    transfer = db.query(Category).filter(Category.household_id == household_id, Category.name == TRANSFER_CATEGORY_NAME).first()
    if transfer is None:
        return 0
    leftovers = db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None), Transaction.amount > 0).all()
    for tx in leftovers:
        tx.category_id = transfer.id
    return len(leftovers)


def rematch_positive_inflows(db: Session, household_id: int, account_ids: list[int]) -> int:
    rules = load_category_rules(db, household_id)
    transfer = db.query(Category).filter(Category.household_id == household_id, Category.name == TRANSFER_CATEGORY_NAME).first()
    transfer_id = transfer.id if transfer is not None else None
    q = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.account_id.in_(account_ids), Transaction.amount > 0)
    if transfer_id is not None:
        q = q.filter(or_(Transaction.category_id.is_(None), Transaction.category_id == transfer_id))
    else:
        q = q.filter(Transaction.category_id.is_(None))
    updated = 0
    for tx in q.all():
        category_id = match_category_with_rules(rules, tx.raw_description, tx.merchant, tx.amount)
        if category_id is None or category_id == tx.category_id:
            continue
        tx.category_id = category_id
        updated += 1
    updated += _assign_leftover_positives_as_transfer(db, household_id, account_ids)
    db.commit()
    return updated


def register_employer_rules(db: Session, household_id: int, companies: list[str]) -> tuple[int, list[str]]:
    income = db.query(Category).filter(Category.household_id == household_id, Category.name == INCOME_CATEGORY_NAME).first()
    if income is None:
        return 0, []
    cleaned = []
    seen: set[str] = set()
    for raw in companies:
        name = raw.strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    existing = {(r.pattern.lower(), r.match_type) for r in db.query(CategoryRule).filter(CategoryRule.category_id == income.id).all()}
    created = 0
    for name in cleaned:
        if (name.lower(), "contains") in existing:
            continue
        db.add(CategoryRule(category_id=income.id, pattern=name[:255], match_type="contains", priority=EMPLOYER_RULE_PRIORITY))
        created += 1
    db.commit()
    return created, cleaned


def classify_uncategorized(db: Session, household_id: int, account_ids: list[int], use_llm: bool = True, max_llm: int | None = None, max_seconds: float | None = None) -> int:
    rules = load_category_rules(db, household_id)
    categories_by_name = _category_by_name(db, household_id)
    known = load_known_commerces(db)
    accounts = load_household_accounts(db, household_id)
    # Newest first so interactive and capped runs prioritize recent spend.
    txs = db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).order_by(Transaction.booked_at.desc(), Transaction.id.desc()).all()
    updated = 0
    llm_queue: list[Transaction] = []
    for tx in txs:
        own_transfer_id = match_own_account_transfer(db, household_id, tx.raw_description, tx.merchant, tx.account_id, accounts)
        if own_transfer_id is not None:
            tx.category_id = own_transfer_id
            updated += 1
            continue
        category_id = match_category_with_rules(rules, tx.raw_description, tx.merchant, tx.amount)
        if category_id is not None:
            tx.category_id = category_id
            updated += 1
            continue
        category_id = match_known_commerce(db, household_id, tx.raw_description, tx.merchant, known, categories_by_name)
        if category_id is not None:
            tx.category_id = category_id
            updated += 1
            continue
        if use_llm and tx.amount < 0:
            llm_queue.append(tx)
    # Persist rule/known matches before slow LLM so assign/sibling updates survive timeouts.
    db.commit()
    if use_llm and llm_queue:
        if max_llm is not None and max_llm >= 0:
            llm_queue = llm_queue[:max_llm]
        updated += _classify_with_llm_batches(db, llm_queue, categories_by_name, max_seconds=max_seconds)
    updated += _assign_leftover_positives_as_transfer(db, household_id, account_ids)
    db.commit()
    return updated


def _classify_with_llm_batches(db: Session, txs: list[Transaction], categories_by_name: dict[str, Category], max_seconds: float | None = None) -> int:
    groups: dict[str, list[Transaction]] = {}
    for tx in txs:
        groups.setdefault(_merchant_key(tx.raw_description, tx.merchant), []).append(tx)
    representatives = [group[0] for group in groups.values()]
    category_by_key: dict[str, int | None] = {}
    deadline = None if max_seconds is None else time.monotonic() + max_seconds
    for offset in range(0, len(representatives), LLM_BATCH_SIZE):
        if deadline is not None and time.monotonic() >= deadline:
            break
        batch = representatives[offset : offset + LLM_BATCH_SIZE]
        items = [(tx.id, tx.raw_description, tx.merchant, tx.amount, tx.currency) for tx in batch]
        results = classify_batch_with_deepseek(items) or {}
        for tx in batch:
            key = _merchant_key(tx.raw_description, tx.merchant)
            category_name = results.get(tx.id)
            if category_name is None:
                category_by_key[key] = None
                continue
            category = categories_by_name.get(category_name)
            if category is None:
                category_by_key[key] = None
                continue
            category_by_key[key] = category.id
            _persist_llm_rule(db, category.id, tx.merchant, tx.raw_description)
            remember_commerce(db, tx.merchant, tx.raw_description, category.name)
    updated = 0
    for key, group in groups.items():
        category_id = category_by_key.get(key)
        if category_id is None:
            continue
        for tx in group:
            tx.category_id = category_id
            updated += 1
    return updated


def backfill_known_commerces(db: Session) -> int:
    known = load_known_commerces(db)
    rows = (
        db.query(Transaction.merchant, Transaction.raw_description, Category.name)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Transaction.category_id.isnot(None), Category.name != TRANSFER_CATEGORY_NAME)
        .all()
    )
    created = 0
    for merchant, description, category_name in rows:
        key = _merchant_key(description, merchant)
        if not key or key in known:
            continue
        remember_commerce(db, merchant, description, category_name)
        known[key] = category_name
        created += 1
    if created:
        db.commit()
    return created
