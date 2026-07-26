from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account, AccountType, User
from app.schemas import ImportResult
from app.services.csv_import import CsvMappingError, import_transactions_csv
from app.services.investment_csv_import import import_investment_balances_csv

router = APIRouter(prefix="/api/import", tags=["import"])
INVESTMENT_ACCOUNT_REQUIRED = "Investment CSV import requires an investment account"


def _household_account(db: Session, account_id: int, household_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    account = _household_account(db, account_id, user.household_id)
    content = (await file.read()).decode("utf-8-sig")
    try:
        imported, skipped, replaced, categorized = import_transactions_csv(db, account, content, overwrite=overwrite)
    except CsvMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ImportResult(imported=imported, skipped=skipped, replaced=replaced, categorized=categorized, account_id=account.id, overwrite=overwrite)


@router.post("/investment-csv", response_model=ImportResult)
async def import_investment_csv(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    account = _household_account(db, account_id, user.household_id)
    if account.account_type != AccountType.investment.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVESTMENT_ACCOUNT_REQUIRED)
    content = (await file.read()).decode("utf-8-sig")
    try:
        imported, skipped, replaced = import_investment_balances_csv(db, account, content, overwrite=overwrite)
    except CsvMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ImportResult(imported=imported, skipped=skipped, replaced=replaced, categorized=0, account_id=account.id, overwrite=overwrite)
