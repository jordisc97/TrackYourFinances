import json
import re
from difflib import get_close_matches

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Category, CategoryRule, Household, Transaction, TransactionSplit, User
from app.schemas import AdvisorActionResult, AdvisorChatIn, AdvisorChatOut
from app.services.dashboard import (
    build_month_rows,
    build_monthly_summary,
    get_or_create_strategy,
    household_account_ids,
    month_transactions,
    spend_by_category,
)
from app.services.deepseek import advisor_chat
from app.services.classification import remember_commerce
from app.services.splits import replace_splits, signed_portion_amount, validate_portions

RECENT_TX_LIMIT = 120
SEARCH_TX_LIMIT = 40
SEARCH_SCAN_LIMIT = 3000
SEARCH_TOKEN_LIMIT = 12
UNCATEGORIZED_SAMPLE = 12
HISTORY_LIMIT = 12
RECATEGORIZE_CAP = 50
SPLIT_CAP = 10
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]{4,}")
STOP_WORDS = {
    "that", "this", "with", "from", "into", "have", "been", "were", "was", "split", "bill", "paid", "rest",
    "ticket", "plane", "wife", "husband", "share", "spent", "spend", "please", "should", "count", "spending",
    "transaction", "transactions", "mark", "move", "make", "assign", "change", "exclude", "account", "about",
    "dont", "does", "will", "want", "them", "they", "then", "than", "also", "just", "only", "over",
}
BANK_NOISE_TOKENS = {
    "compra", "targ", "tarjeta", "pago", "recibo", "adeudo", "cargo", "abono", "transfer", "transferencia",
    "visa", "mastercard", "debit", "credit", "card", "banco", "bank", "atm", "cash", "withdrawal",
}


def _resolve_category(name: str, categories: list[Category]) -> Category | None:
    needle = name.strip().lower()
    if not needle or not categories:
        return None
    by_lower = {c.name.lower(): c for c in categories}
    exact = by_lower.get(needle)
    if exact is not None:
        return exact
    contains = [c for c in categories if needle in c.name.lower() or c.name.lower() in needle]
    if len(contains) == 1:
        return contains[0]
    token_hits = [c for c in categories if any(tok.startswith(needle) or needle.startswith(tok) for tok in c.name.lower().replace("&", " ").split() if len(tok) > 2)]
    if len(token_hits) == 1:
        return token_hits[0]
    pool = contains or token_hits or categories
    matches = get_close_matches(needle, [c.name.lower() for c in pool], n=1, cutoff=0.35)
    return next((c for c in pool if c.name.lower() == matches[0]), None) if matches else None


def _tx_line(tx: Transaction) -> dict:
    splits = [
        {
            "amount": round(s.amount, 2),
            "label": s.label,
            "category": s.category.name if s.category else (tx.category.name if tx.category else None),
        }
        for s in (tx.splits or [])
    ]
    return {
        "id": tx.id,
        "date": tx.booked_at.isoformat(),
        "amount": round(tx.amount, 2),
        "currency": tx.currency,
        "merchant": (tx.merchant or "")[:80],
        "description": (tx.raw_description or "")[:100],
        "category": tx.category.name if tx.category else None,
        "splits": splits,
    }


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _search_tokens(message: str) -> list[str]:
    raw = [t.lower() for t in TOKEN_RE.findall(message or "") if t.lower() not in STOP_WORDS]
    unique = _dedupe_tokens(raw)
    distinctive = [t for t in unique if t not in BANK_NOISE_TOKENS]
    ranked = sorted(distinctive or unique, key=len, reverse=True)
    return ranked[:SEARCH_TOKEN_LIMIT]


def _match_score(hay: str, tokens: list[str]) -> int:
    hits = [token for token in tokens if token in hay]
    if not hits:
        return 0
    return sum(len(token) * len(token) for token in hits)


def _matching_transactions(db: Session, account_ids: list[int], tokens: list[str]) -> list[Transaction]:
    if not account_ids or not tokens:
        return []
    txs = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
        .filter(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.booked_at.desc())
        .limit(SEARCH_SCAN_LIMIT)
        .all()
    )
    scored = [(_match_score(f"{tx.merchant} {tx.raw_description}".lower(), tokens), tx) for tx in txs]
    scored = [(score, tx) for score, tx in scored if score > 0]
    scored.sort(key=lambda item: (item[0], item[1].booked_at), reverse=True)
    return [tx for _, tx in scored[:SEARCH_TX_LIMIT]]


def build_advisor_context(db: Session, household_id: int, year: int, month: int, message: str = "") -> dict:
    household = db.get(Household, household_id)
    account_ids = household_account_ids(db, household_id)
    categories = db.query(Category).filter(Category.household_id == household_id).order_by(Category.name).all()
    month_txs = month_transactions(db, household_id, year, month)
    strategy = get_or_create_strategy(db, household_id, year, month)
    month_rows = build_month_rows(db, household_id)
    summary = build_monthly_summary(db, household_id, year, month, month_txs, strategy, month_rows)
    category_spend = spend_by_category(month_txs)
    recent_q = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
        .filter(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.booked_at.desc())
        .limit(RECENT_TX_LIMIT)
    )
    recent = recent_q.all() if account_ids else []
    uncategorized = [t for t in recent if t.category_id is None]
    uncategorized_count = (
        db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).count()
        if account_ids
        else 0
    )
    matched = _matching_transactions(db, account_ids, _search_tokens(message))
    return {
        "household": household.name if household else "",
        "location": (household.location or "") if household else "",
        "period": {"year": year, "month": month},
        "summary": {
            "income": summary.income,
            "real_spend": summary.real_spend,
            "save_amount": summary.save_amount,
            "save_pct": summary.save_pct,
            "net_worth": summary.net_worth,
            "actual_spend_pct": summary.actual_spend_pct,
            "actual_save_pct": summary.actual_save_pct,
            "actual_invest_pct": summary.actual_invest_pct,
            "recommended_spend": summary.recommended_spend,
            "recommended_save": summary.recommended_save,
            "recommended_invest": summary.recommended_invest,
        },
        "strategy": {
            "spend_pct": strategy.spend_pct,
            "save_pct": strategy.save_pct,
            "invest_pct": strategy.invest_pct,
        },
        "spend_by_category": [
            {
                "name": row.category_name,
                "amount": row.amount,
                "pct": row.pct,
                "benchmark_amount": row.benchmark_amount,
            }
            for row in category_spend
        ],
        "categories": [{"id": c.id, "name": c.name, "kind": c.kind} for c in categories],
        "recent_transactions": [_tx_line(t) for t in recent],
        "matched_transactions": [_tx_line(t) for t in matched],
        "uncategorized_count": uncategorized_count,
        "uncategorized_sample": [_tx_line(t) for t in uncategorized[:UNCATEGORIZED_SAMPLE]],
        "capabilities": ["recategorize", "split"],
    }


def _system_prompt(context: dict) -> str:
    return (
        "You are a concise household financial advisor inside TrackYourFinances. "
        "Always reply in short bullet points only — no paragraphs, no long explanations. "
        "Keep each bullet to one short sentence; prefer 2–5 bullets total. "
        "Use only the provided JSON context; never invent balances or transactions. "
        "Give practical advice on spending, saving, investing, categorization, and bill splits. "
        "When the user asks to move transactions to a category, map their wording to the closest existing category name from context.categories. "
        "Never create new categories. "
        "You CAN split one transaction into labeled portions. Bank amount stays unchanged; portion amounts must sum to the transaction amount (same sign). "
        "Use expense categories for portions that should count as spending (including money paid for a partner). "
        "Use Transfer only when a portion should be excluded from spend, or when the user asks not to count a charge as spend. "
        "matched_transactions is month-independent: when the user names a merchant or pastes a bank description, use those ids for recategorize/split even if the date is outside period. "
        "Do not refuse a clear recategorize/split request only because the charge is outside the selected month. "
        'Reply with JSON only: {"reply":"<plain text for the user>","actions":[{"type":"recategorize","transaction_ids":[1],"category_name":"<name>","create_rule":true},{"type":"split","transaction_id":1,"portions":[{"amount":-521,"label":"Me","category_name":"Travel"},{"amount":-479,"label":"Wife","category_name":"Travel"}]}]}. '
        "Use actions only when the user clearly wants recategorization or a split; otherwise actions must be []. "
        f"Context: {json.dumps(context, separators=(',', ':'))}"
    )


def _parse_advisor_json(content: str) -> tuple[str, list[dict]]:
    match = JSON_OBJECT_RE.search(content or "")
    if not match:
        return (content or "").strip() or "I could not produce a response.", []
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return (content or "").strip() or "I could not produce a response.", []
    if not isinstance(payload, dict):
        return (content or "").strip() or "I could not produce a response.", []
    reply = str(payload.get("reply") or "").strip() or "Done."
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    return reply, [a for a in actions if isinstance(a, dict)]


def _apply_recategorize(
    db: Session,
    account_ids: list[int],
    categories: list[Category],
    action: dict,
    remaining: int,
) -> AdvisorActionResult:
    category = _resolve_category(str(action.get("category_name") or ""), categories)
    if category is None:
        return AdvisorActionResult(type="recategorize", detail="No matching category found")
    raw_ids = action.get("transaction_ids") if isinstance(action.get("transaction_ids"), list) else []
    ids: list[int] = []
    for x in raw_ids:
        if isinstance(x, bool):
            continue
        if isinstance(x, (int, float)):
            ids.append(int(x))
        elif isinstance(x, str) and x.strip().lstrip("-").isdigit():
            ids.append(int(x.strip()))
    ids = ids[:remaining]
    if not ids or not account_ids:
        return AdvisorActionResult(type="recategorize", category_name=category.name, detail="No transactions to update")
    txs = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(Transaction.id.in_(ids), Transaction.account_id.in_(account_ids))
        .all()
    )
    create_rule = bool(action.get("create_rule", True))
    updated_ids: list[int] = []
    for tx in txs:
        tx.category_id = category.id
        updated_ids.append(tx.id)
        remember_commerce(db, tx.merchant, tx.raw_description, category.name)
        if create_rule:
            pattern = (tx.merchant or tx.raw_description or "").strip()[:255]
            if pattern:
                db.add(CategoryRule(category_id=category.id, pattern=pattern, match_type="contains", priority=50))
    if updated_ids:
        db.commit()
    return AdvisorActionResult(
        type="recategorize",
        count=len(updated_ids),
        category_name=category.name,
        transaction_ids=updated_ids,
        detail=f"Updated {len(updated_ids)} to {category.name}" if updated_ids else "No matching transactions",
    )


def _parse_tx_id(raw) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    return None


def _apply_split(db: Session, account_ids: list[int], categories: list[Category], action: dict) -> AdvisorActionResult:
    tx_id = _parse_tx_id(action.get("transaction_id"))
    raw_portions = action.get("portions") if isinstance(action.get("portions"), list) else []
    if tx_id is None or not account_ids:
        return AdvisorActionResult(type="split", detail="Missing transaction_id")
    tx = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
        .filter(Transaction.id == tx_id, Transaction.account_id.in_(account_ids))
        .first()
    )
    if tx is None:
        return AdvisorActionResult(type="split", detail="Transaction not found")
    categories_by_id = {c.id: c for c in categories}
    portions: list[dict] = []
    for item in raw_portions:
        if not isinstance(item, dict):
            continue
        amount_raw = item.get("amount")
        if not isinstance(amount_raw, (int, float)):
            continue
        category = _resolve_category(str(item.get("category_name") or ""), categories)
        category_id = category.id if category is not None else tx.category_id
        portions.append(
            {
                "amount": signed_portion_amount(tx.amount, float(amount_raw)),
                "label": str(item.get("label") or "Share")[:120],
                "category_id": category_id,
            }
        )
    error = validate_portions(tx, portions, categories_by_id)
    if error:
        return AdvisorActionResult(type="split", transaction_ids=[tx.id], detail=error)
    replace_splits(db, tx, portions)
    labels = ", ".join(f"{p['label']} {abs(p['amount']):.2f}" for p in portions)
    return AdvisorActionResult(type="split", count=1, transaction_ids=[tx.id], detail=f"Split into {labels}")


def run_advisor_chat(db: Session, user: User, payload: AdvisorChatIn) -> AdvisorChatOut:
    settings = get_settings()
    if not settings.deepseek_api:
        return AdvisorChatOut(reply="DeepSeek is not configured. Set DEEPSEEK_API in the backend environment.")
    context = build_advisor_context(db, user.household_id, payload.year, payload.month, payload.message)
    history = payload.history[-HISTORY_LIMIT:]
    messages: list[dict[str, str]] = [{"role": "system", "content": _system_prompt(context)}]
    for item in history:
        role = item.role if item.role in ("user", "assistant") else "user"
        messages.append({"role": role, "content": item.content[:4000]})
    messages.append({"role": "user", "content": payload.message.strip()[:4000]})
    content = advisor_chat(messages)
    if not content:
        return AdvisorChatOut(reply="The advisor could not reach DeepSeek right now. Try again in a moment.")
    reply, actions = _parse_advisor_json(content)
    account_ids = household_account_ids(db, user.household_id)
    categories = db.query(Category).filter(Category.household_id == user.household_id).all()
    results: list[AdvisorActionResult] = []
    remaining = RECATEGORIZE_CAP
    splits_left = SPLIT_CAP
    for action in actions:
        action_type = action.get("type")
        if action_type == "recategorize" and remaining > 0:
            result = _apply_recategorize(db, account_ids, categories, action, remaining)
            remaining -= result.count
            results.append(result)
        elif action_type == "split" and splits_left > 0:
            result = _apply_split(db, account_ids, categories, action)
            splits_left -= result.count
            results.append(result)
    mutated = any(r.count > 0 for r in results)
    return AdvisorChatOut(reply=reply, action_results=results, mutated=mutated)
