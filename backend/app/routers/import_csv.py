from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account, User
from app.schemas import ImportResult
from app.services.csv_import import CsvMappingError, import_transactions_csv

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == user.household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    content = (await file.read()).decode("utf-8-sig")
    try:
        imported, skipped = import_transactions_csv(db, account, content)
    except CsvMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ImportResult(imported=imported, skipped=skipped, account_id=account.id)
