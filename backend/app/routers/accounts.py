from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account, BalanceSnapshot, User
from app.schemas import AccountCreate, AccountOut, BalanceIn, BalanceOut
from app.services.dashboard import latest_balances
from app.services.sync import upsert_balance

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AccountOut]:
    accounts = db.query(Account).filter(Account.household_id == user.household_id, Account.is_active.is_(True)).all()
    balances = latest_balances(db, user.household_id)
    return [
        AccountOut(id=a.id, name=a.name, institution=a.institution, currency=a.currency, account_type=a.account_type, source=a.source, is_active=a.is_active, latest_balance=balances.get(a.id, 0.0))
        for a in accounts
    ]


@router.post("", response_model=AccountOut)
def create_account(payload: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AccountOut:
    account = Account(household_id=user.household_id, name=payload.name, institution=payload.institution, currency=payload.currency, account_type=payload.account_type, source=payload.source)
    db.add(account)
    db.commit()
    db.refresh(account)
    return AccountOut(id=account.id, name=account.name, institution=account.institution, currency=account.currency, account_type=account.account_type, source=account.source, is_active=account.is_active, latest_balance=0.0)


@router.post("/{account_id}/balances", response_model=BalanceOut)
def add_balance(account_id: int, payload: BalanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BalanceSnapshot:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == user.household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    upsert_balance(db, account, payload.amount, payload.snapshot_date or date.today())
    db.commit()
    snap = db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account.id, BalanceSnapshot.snapshot_date == (payload.snapshot_date or date.today())).one()
    return snap
