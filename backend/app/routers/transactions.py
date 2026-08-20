from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Account, Category, Transaction, TransactionSplit, User
from app.schemas import (
    CategoryOut,
    ClassifyResult,
    EmployersIn,
    EmployersOut,
    TransactionAssignIn,
    TransactionOut,
    TransactionSplitIn,
    TransactionSplitOut,
)
from app.services.classification import (
    apply_pattern_to_uncategorized,
    classify_uncategorized,
    ensure_contains_rule,
    merchant_match_pattern,
    remember_commerce,
    rematch_positive_inflows,
    register_employer_rules,
)
from app.services.dashboard import household_account_ids, is_spend_outflow
from app.services.splits import clear_splits, replace_splits, signed_portion_amount, validate_portions

router = APIRouter(prefix="/api", tags=["transactions"])


def _household_account_ids(db: Session, user: User) -> list[int]:
    return household_account_ids(db, user.household_id)


def _split_out(split: TransactionSplit) -> TransactionSplitOut:
    return TransactionSplitOut(
        id=split.id,
        amount=split.amount,
        label=split.label,
        category_id=split.category_id,
        category_name=split.category.name if split.category else None,
        category_kind=split.category.kind if split.category else None,
        sort_order=split.sort_order,
    )


def _tx_out(tx: Transaction) -> TransactionOut:
    splits = [_split_out(s) for s in (tx.splits or [])]
    return TransactionOut(
        id=tx.id,
        account_id=tx.account_id,
        category_id=tx.category_id,
        booked_at=tx.booked_at,
        amount=tx.amount,
        currency=tx.currency,
        raw_description=tx.raw_description,
        merchant=tx.merchant,
        counterparty=tx.counterparty or "",
        counterparty_iban=tx.counterparty_iban or "",
        location=tx.location or "",
        mcc=tx.mcc,
        value_date=tx.value_date,
        balance_after=tx.balance_after,
        source=tx.source,
        category_name=tx.category.name if tx.category else None,
        category_kind=tx.category.kind if tx.category else None,
        splits=splits,
    )


def _tx_query(db: Session, account_ids: list[int]):
    return db.query(Transaction).options(
        joinedload(Transaction.category),
        joinedload(Transaction.splits).joinedload(TransactionSplit.category),
    ).filter(Transaction.account_id.in_(account_ids))


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    uncategorized: bool = False,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    category_id: int | None = Query(None),
    uncategorized_only: bool = Query(False),
    expenses_only: bool = Query(False),
    q: str | None = Query(None),
    limit: int = Query(200, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionOut]:
    account_ids = _household_account_ids(db, user)
    if not account_ids:
        return []
    query = _tx_query(db, account_ids)
    if uncategorized or uncategorized_only:
        query = query.filter(Transaction.category_id.is_(None))
    if year is not None and month is not None:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        query = query.filter(Transaction.booked_at >= start, Transaction.booked_at <= end)
    if expenses_only:
        query = query.filter(Transaction.amount < 0)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            (Transaction.merchant.ilike(needle))
            | (Transaction.raw_description.ilike(needle))
            | (Transaction.counterparty.ilike(needle))
            | (Transaction.location.ilike(needle))
        )
    txs = query.order_by(Transaction.booked_at.desc()).limit(limit).all()
    if expenses_only:
        txs = [tx for tx in txs if is_spend_outflow(tx)]
    if category_id is not None:
        txs = [
            tx for tx in txs
            if tx.category_id == category_id or any(s.category_id == category_id for s in (tx.splits or []))
        ]
    return [_tx_out(t) for t in txs]


@router.post("/transactions/{transaction_id}/assign", response_model=TransactionOut)
def assign_category(transaction_id: int, payload: TransactionAssignIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TransactionOut:
    account_ids = _household_account_ids(db, user)
    tx = (
        db.query(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account), joinedload(Transaction.splits).joinedload(TransactionSplit.category))
        .filter(Transaction.id == transaction_id, Transaction.account_id.in_(account_ids))
        .first()
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    category = db.query(Category).filter(Category.id == payload.category_id, Category.household_id == user.household_id).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    tx.category_id = category.id
    remember_commerce(db, tx.merchant, tx.raw_description, category.name)
    pattern = payload.rule_pattern or merchant_match_pattern(tx.merchant, tx.raw_description) or (tx.merchant or tx.raw_description)
    if payload.create_rule and pattern:
        ensure_contains_rule(db, category.id, pattern)
    apply_pattern_to_uncategorized(db, account_ids, category.id, pattern or "")
    db.commit()
    classify_uncategorized(db, user.household_id, account_ids, use_llm=False)
    tx = _tx_query(db, account_ids).filter(Transaction.id == transaction_id).one()
    return _tx_out(tx)


@router.post("/transactions/{transaction_id}/split", response_model=TransactionOut)
def split_transaction(transaction_id: int, payload: TransactionSplitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TransactionOut:
    account_ids = _household_account_ids(db, user)
    tx = _tx_query(db, account_ids).filter(Transaction.id == transaction_id).first()
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    categories = db.query(Category).filter(Category.household_id == user.household_id).all()
    categories_by_id = {c.id: c for c in categories}
    portions = [
        {"amount": signed_portion_amount(tx.amount, p.amount), "label": p.label, "category_id": p.category_id}
        for p in payload.portions
    ]
    error = validate_portions(tx, portions, categories_by_id)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    updated = replace_splits(db, tx, portions)
    return _tx_out(updated)


@router.delete("/transactions/{transaction_id}/split", response_model=TransactionOut)
def unsplit_transaction(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TransactionOut:
    account_ids = _household_account_ids(db, user)
    tx = _tx_query(db, account_ids).filter(Transaction.id == transaction_id).first()
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    updated = clear_splits(db, tx)
    return _tx_out(updated)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Category]:
    return db.query(Category).filter(Category.household_id == user.household_id).order_by(Category.name).all()


@router.post("/categories/employers", response_model=EmployersOut)
def register_employers(payload: EmployersIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> EmployersOut:
    created, companies = register_employer_rules(db, user.household_id, payload.companies)
    if companies:
        account_ids = _household_account_ids(db, user)
        if account_ids:
            rematch_positive_inflows(db, user.household_id, account_ids)
    return EmployersOut(created=created, companies=companies)


@router.post("/transactions/classify", response_model=ClassifyResult)
def classify_transactions(account_id: int | None = Query(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ClassifyResult:
    accounts = db.query(Account).filter(Account.household_id == user.household_id, Account.is_active.is_(True)).all()
    if account_id is not None:
        accounts = [account for account in accounts if account.id == account_id]
    if not accounts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    account_ids = [account.id for account in accounts]
    max_seconds = get_settings().categorize_max_seconds
    categorized = classify_uncategorized(db, user.household_id, account_ids, use_llm=True, max_seconds=max_seconds)
    remaining = db.query(Transaction).filter(Transaction.account_id.in_(account_ids), Transaction.category_id.is_(None)).count()
    return ClassifyResult(categorized=categorized, account_id=account_id, remaining=remaining)
