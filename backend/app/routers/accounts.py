from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account, BalanceSnapshot, User
from app.schemas import AccountCreate, AccountFlowOut, AccountOut, AccountUpdate, BalanceIn, BalanceOut
from app.services.account_purge import purge_account_data, purge_inactive_accounts
from app.services.accounts_helpers import normalize_iban
from app.services.dashboard import latest_balances
from app.services.flow import build_account_flow, reclassify_own_account_transfers
from app.services.sync import upsert_balance

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
ACCOUNT_NOT_FOUND = "Account not found"


def _account_out(account: Account, latest_balance: float | None = None) -> AccountOut:
    return AccountOut(
        id=account.id,
        name=account.name,
        institution=account.institution,
        currency=account.currency,
        account_type=account.account_type,
        source=account.source,
        is_active=account.is_active,
        iban=account.iban,
        latest_balance=latest_balance,
    )


@router.get("", response_model=list[AccountOut])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AccountOut]:
    if purge_inactive_accounts(db, user.household_id):
        db.commit()
    accounts = db.query(Account).filter(Account.household_id == user.household_id, Account.is_active.is_(True)).all()
    balances = latest_balances(db, user.household_id)
    return [_account_out(a, balances.get(a.id, 0.0)) for a in accounts]


@router.get("/flow", response_model=AccountFlowOut)
def account_flow(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountFlowOut:
    return build_account_flow(db, user.household_id, year, month)


@router.post("", response_model=AccountOut)
def create_account(payload: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AccountOut:
    account = Account(
        household_id=user.household_id,
        name=payload.name,
        institution=payload.institution,
        currency=payload.currency,
        account_type=payload.account_type,
        source=payload.source,
        iban=normalize_iban(payload.iban),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    if account.iban:
        reclassify_own_account_transfers(db, user.household_id)
    return _account_out(account, 0.0)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, payload: AccountUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AccountOut:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == user.household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ACCOUNT_NOT_FOUND)
    iban_changed = False
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        account.name = data["name"]
    if "institution" in data:
        account.institution = data["institution"]
    if "account_type" in data:
        account.account_type = data["account_type"]
    if "iban" in data:
        new_iban = normalize_iban(data["iban"])
        iban_changed = new_iban != account.iban
        account.iban = new_iban
    if "is_active" in data:
        account.is_active = bool(data["is_active"])
    db.commit()
    db.refresh(account)
    if iban_changed or "name" in data:
        reclassify_own_account_transfers(db, user.household_id)
    balances = latest_balances(db, user.household_id)
    return _account_out(account, balances.get(account.id, 0.0))


@router.delete("/{account_id}", response_model=AccountOut)
def delete_account(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AccountOut:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == user.household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ACCOUNT_NOT_FOUND)
    result = _account_out(account, 0.0)
    purge_account_data(db, account)
    db.commit()
    return result


@router.post("/{account_id}/balances", response_model=BalanceOut)
def add_balance(account_id: int, payload: BalanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BalanceSnapshot:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == user.household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ACCOUNT_NOT_FOUND)
    upsert_balance(db, account, payload.amount, payload.snapshot_date or date.today())
    db.commit()
    snap = db.query(BalanceSnapshot).filter(BalanceSnapshot.account_id == account.id, BalanceSnapshot.snapshot_date == (payload.snapshot_date or date.today())).one()
    return snap
