from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account, AccountType, User
from app.schemas import ImportResult, RevolutImportPreview
from app.services.csv_import import CsvMappingError, import_transactions_upload
from app.services.investment_csv_import import import_investment_balances_csv
from app.services.revolut_robo_import import import_revolut_robo_csv, preview_revolut_robo_csv

router = APIRouter(prefix="/api/import", tags=["import"])
INVESTMENT_ACCOUNT_REQUIRED = "Investment CSV import requires an investment account"


def _household_account(db: Session, account_id: int, household_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id, Account.household_id == household_id).first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


def _summary_fields(summary) -> dict:
    return {
        "account_type": summary.account_type,
        "format_detected": summary.format_detected,
        "transactions": summary.transactions,
        "contributions": summary.contributions,
        "purchases": summary.purchases,
        "dividends": summary.dividends,
        "management_fees": summary.management_fees,
        "securities": summary.securities,
        "currency": summary.currency,
        "unknown_types": summary.unknown_types,
    }


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    account = _household_account(db, account_id, user.household_id)
    try:
        content_bytes = await file.read()
        filename = file.filename or ""
        imported, skipped, replaced, categorized = import_transactions_upload(db, account, filename, content_bytes, overwrite=overwrite)
    except CsvMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Import failed: {exc}") from exc
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


@router.post("/revolut-preview", response_model=RevolutImportPreview)
async def revolut_preview(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> RevolutImportPreview:
    content_bytes = await file.read()
    try:
        summary = preview_revolut_robo_csv(content_bytes)
    except CsvMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RevolutImportPreview(**_summary_fields(summary))


@router.post("/revolut-csv", response_model=ImportResult)
async def import_revolut_csv(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    account = _household_account(db, account_id, user.household_id)
    if account.account_type != AccountType.investment.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVESTMENT_ACCOUNT_REQUIRED)
    content_bytes = await file.read()
    try:
        imported, skipped, replaced, categorized, summary = import_revolut_robo_csv(db, account, content_bytes, overwrite=overwrite)
    except CsvMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Import failed: {exc}") from exc
    return ImportResult(
        imported=imported,
        skipped=skipped,
        replaced=replaced,
        categorized=categorized,
        account_id=account.id,
        overwrite=overwrite,
        **_summary_fields(summary),
    )
