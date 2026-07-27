import json
import re
from difflib import get_close_matches

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Category, CategoryRule, Household, Transaction, User
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

RECENT_TX_LIMIT = 80
UNCATEGORIZED_SAMPLE = 12
HISTORY_LIMIT = 12
RECATEGORIZE_CAP = 50
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


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
    return {
        "id": tx.id,
        "date": tx.booked_at.isoformat(),
        "amount": round(tx.amount, 2),
        "currency": tx.currency,
        "merchant": (tx.merchant or "")[:80],
        "description": (tx.raw_description or "")[:100],
        "category": tx.category.name if tx.category else None,
    }


def build_advisor_context(db: Session, household_id: int, year: int, month: int) -> dict:
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
        .options(joinedload(Transaction.category))
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
        "uncategorized_count": uncategorized_count,
        "uncategorized_sample": [_tx_line(t) for t in uncategorized[:UNCATEGORIZED_SAMPLE]],
    }


def _system_prompt(context: dict) -> str:
    return (
        "You are a concise household financial advisor inside TrackYourFinances. "
        "Use only the provided JSON context; never invent balances or transactions. "
        "Give practical advice on spending, saving, investing, and categorization. "
        "When the user asks to move transactions to a category, map their wording to the closest existing category name from context.categories. "
        "Never create new categories. "
        'Reply with JSON only: {"reply":"<plain text for the user>","actions":[{"type":"recategorize","transaction_ids":[1],"category_name":"<exact or close name>","create_rule":true}]}. '
        "Use actions only when the user clearly wants recategorization; otherwise actions must be []. "
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


def run_advisor_chat(db: Session, user: User, payload: AdvisorChatIn) -> AdvisorChatOut:
    settings = get_settings()
    if not settings.deepseek_api:
        return AdvisorChatOut(reply="DeepSeek is not configured. Set DEEPSEEK_API in the backend environment.")
    context = build_advisor_context(db, user.household_id, payload.year, payload.month)
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
    for action in actions:
        if remaining <= 0:
            break
        if action.get("type") != "recategorize":
            continue
        result = _apply_recategorize(db, account_ids, categories, action, remaining)
        remaining -= result.count
        results.append(result)
    mutated = any(r.count > 0 for r in results)
    return AdvisorChatOut(reply=reply, action_results=results, mutated=mutated)
