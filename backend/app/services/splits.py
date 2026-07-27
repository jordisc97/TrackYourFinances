from sqlalchemy.orm import Session, joinedload

from app.models import Category, Transaction, TransactionSplit

AMOUNT_TOLERANCE = 0.02
DEFAULT_SPLIT_LABEL = "Share"
MIN_PORTIONS = 2


def load_tx_with_splits(db: Session, transaction_id: int) -> Transaction | None:
    return (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
        .filter(Transaction.id == transaction_id)
        .first()
    )


def validate_portions(tx: Transaction, portions: list[dict], categories_by_id: dict[int, Category]) -> str | None:
    if len(portions) < MIN_PORTIONS:
        return "A split needs at least two portions"
    signed_total = round(sum(float(p["amount"]) for p in portions), 2)
    if abs(signed_total - round(float(tx.amount), 2)) > AMOUNT_TOLERANCE:
        return f"Split amounts must sum to {tx.amount}, got {signed_total}"
    for portion in portions:
        category_id = portion.get("category_id")
        if category_id is not None and category_id not in categories_by_id:
            return "Unknown category in split"
        if float(portion["amount"]) == 0:
            return "Split portions cannot be zero"
        if float(tx.amount) != 0 and (float(portion["amount"]) > 0) != (float(tx.amount) > 0):
            return "Split portions must share the transaction sign"
    return None


def replace_splits(db: Session, tx: Transaction, portions: list[dict]) -> Transaction:
    db.query(TransactionSplit).filter(TransactionSplit.transaction_id == tx.id).delete()
    for index, portion in enumerate(portions):
        label = str(portion.get("label") or DEFAULT_SPLIT_LABEL).strip()[:120] or DEFAULT_SPLIT_LABEL
        category_id = portion.get("category_id") if portion.get("category_id") is not None else tx.category_id
        db.add(TransactionSplit(transaction_id=tx.id, amount=round(float(portion["amount"]), 2), label=label, category_id=category_id, sort_order=index))
    primary = next((p for p in portions if float(p["amount"]) < 0), portions[0])
    if primary.get("category_id") is not None:
        tx.category_id = primary["category_id"]
    db.commit()
    return load_tx_with_splits(db, tx.id) or tx


def clear_splits(db: Session, tx: Transaction) -> Transaction:
    db.query(TransactionSplit).filter(TransactionSplit.transaction_id == tx.id).delete()
    db.commit()
    return load_tx_with_splits(db, tx.id) or tx


def signed_portion_amount(parent_amount: float, portion_amount: float) -> float:
    magnitude = abs(float(portion_amount))
    if parent_amount < 0:
        return -magnitude
    if parent_amount > 0:
        return magnitude
    return float(portion_amount)
