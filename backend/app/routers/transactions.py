from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.models import Account, Category, CategoryRule, Transaction, User
from app.schemas import CategoryOut, CategoryRuleIn, CategoryRuleOut, TransactionAssignIn, TransactionCreate, TransactionOut
from app.services.classification import classify_uncategorized

router = APIRouter(prefix="/api", tags=["transactions"])


def _tx_out(tx: Transaction) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        account_id=tx.account_id,
        category_id=tx.category_id,
        booked_at=tx.booked_at,
        amount=tx.amount,
        currency=tx.currency,
        raw_description=tx.raw_description,
        merchant=tx.merchant,
        source=tx.source,
        category_name=tx.category.name if tx.category else None,
    )


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    uncategorized: bool = False,
    limit: int = Query(200, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionOut]:
    account_ids = [a.id for a in db.query(Account).filter(Account.household_id == user.household_id).all()]
    if not account_ids:
        return []
    q = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.account_id.in_(account_ids))
    if uncategorized:
        q = q.filter(Transaction.category_id.is_(None))
    txs = q.order_by(Transaction.booked_at.desc()).limit(limit).all()
    return [_tx_out(t) for t in txs]


@router.post("/transactions", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TransactionOut:
    account = db.query(Account).filter(Account.id == payload.account_id, Account.household_id == user.household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    tx = Transaction(account_id=payload.account_id, booked_at=payload.booked_at, amount=payload.amount, currency=payload.currency, raw_description=payload.raw_description, merchant=payload.merchant, category_id=payload.category_id, source="manual")
    db.add(tx)
    db.commit()
    db.refresh(tx)
    tx = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.id == tx.id).one()
    return _tx_out(tx)


@router.post("/transactions/{transaction_id}/assign", response_model=TransactionOut)
def assign_category(transaction_id: int, payload: TransactionAssignIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TransactionOut:
    tx = db.query(Transaction).options(joinedload(Transaction.category), joinedload(Transaction.account)).filter(Transaction.id == transaction_id).first()
    if tx is None or tx.account.household_id != user.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    category = db.query(Category).filter(Category.id == payload.category_id, Category.household_id == user.household_id).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    tx.category_id = category.id
    if payload.create_rule:
        pattern = payload.rule_pattern or tx.merchant or tx.raw_description
        if pattern:
            db.add(CategoryRule(category_id=category.id, pattern=pattern[:255], match_type="contains", priority=50))
    db.commit()
    account_ids = [a.id for a in db.query(Account).filter(Account.household_id == user.household_id).all()]
    classify_uncategorized(db, user.household_id, account_ids)
    tx = db.query(Transaction).options(joinedload(Transaction.category)).filter(Transaction.id == transaction_id).one()
    return _tx_out(tx)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Category]:
    return db.query(Category).filter(Category.household_id == user.household_id).order_by(Category.name).all()


@router.get("/category-rules", response_model=list[CategoryRuleOut])
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[CategoryRule]:
    return db.query(CategoryRule).join(Category).filter(Category.household_id == user.household_id).order_by(CategoryRule.priority).all()


@router.post("/categories/{category_id}/rules", response_model=CategoryRuleOut)
def add_rule(category_id: int, payload: CategoryRuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CategoryRule:
    category = db.query(Category).filter(Category.id == category_id, Category.household_id == user.household_id).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    rule = CategoryRule(category_id=category.id, pattern=payload.pattern, match_type=payload.match_type, priority=payload.priority)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule
