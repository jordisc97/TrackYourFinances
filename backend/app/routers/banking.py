from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import BankConnection, ConnectionStatus, User
from app.providers.enable_banking import get_bank_provider
from app.schemas import AuthStartOut, BankConnectionOut, InstitutionOut
from app.services.sync import sync_connection

router = APIRouter(prefix="/api/banking", tags=["banking"])


def _frontend_url(path_query: str) -> str:
    frontend = get_settings().cors_origins.split(",")[0].strip().rstrip("/")
    return f"{frontend}{path_query}"


def _banks_redirect(status_value: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=_frontend_url(f"/banks?bank_status={status_value}&bank_message={quote(message)}"))


@router.get("/institutions", response_model=list[InstitutionOut])
def institutions(user: User = Depends(get_current_user)) -> list[InstitutionOut]:
    settings = get_settings()
    provider = get_bank_provider()
    return [InstitutionOut(id=i.id, name=i.name, country=i.country, logo=i.logo) for i in provider.list_institutions(settings.enable_banking_country)]


@router.get("/connections", response_model=list[BankConnectionOut])
def connections(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BankConnection]:
    return db.query(BankConnection).filter(BankConnection.household_id == user.household_id).all()


@router.post("/connect/{institution_id}", response_model=AuthStartOut)
def connect(institution_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthStartOut:
    provider = get_bank_provider()
    institutions = {i.id: i for i in provider.list_institutions(get_settings().enable_banking_country)}
    institution = institutions.get(institution_id)
    if institution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    connection = BankConnection(
        household_id=user.household_id,
        provider=provider.name,
        institution_id=institution.id,
        institution_name=institution.name,
        status=ConnectionStatus.pending.value,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    session = provider.start_authorization(institution.id, state=str(connection.id))
    connection.session_id = session.session_id
    db.commit()
    return AuthStartOut(authorization_url=session.authorization_url, connection_id=connection.id)


@router.get("/callback")
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        if state and state.isdigit():
            connection = db.get(BankConnection, int(state))
            if connection is not None:
                connection.status = ConnectionStatus.error.value
                db.commit()
        detail = error_description or error
        message = "Bank login was cancelled. You can retry from Banks, or import a CSV instead." if error == "access_denied" else f"Bank login failed: {detail}"
        return _banks_redirect("failed", message)
    if not state or not state.isdigit():
        return _banks_redirect("failed", "Missing bank connection state.")
    connection = db.get(BankConnection, int(state))
    if connection is None:
        return _banks_redirect("failed", "Bank connection not found.")
    if not code:
        connection.status = ConnectionStatus.error.value
        db.commit()
        return _banks_redirect("failed", "Bank login did not return an authorization code. Try again.")
    provider = get_bank_provider()
    result = provider.complete_authorization(code, state, connection.session_id or "")
    connection.session_id = result.session_id
    connection.consent_expires_at = result.consent_expires_at
    connection.status = ConnectionStatus.active.value
    db.commit()
    sync_connection(db, connection, provider)
    return _banks_redirect("connected", f"Connected {connection.institution_name}.")


@router.post("/connections/{connection_id}/sync")
def sync(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    connection = db.query(BankConnection).filter(BankConnection.id == connection_id, BankConnection.household_id == user.household_id).first()
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    imported = sync_connection(db, connection, get_bank_provider())
    return {"imported": imported, "status": connection.status}


@router.post("/connections/{connection_id}/reconnect", response_model=AuthStartOut)
def reconnect(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthStartOut:
    connection = db.query(BankConnection).filter(BankConnection.id == connection_id, BankConnection.household_id == user.household_id).first()
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    provider = get_bank_provider()
    session = provider.start_authorization(connection.institution_id, state=str(connection.id))
    connection.session_id = session.session_id
    connection.status = ConnectionStatus.pending.value
    db.commit()
    return AuthStartOut(authorization_url=session.authorization_url, connection_id=connection.id)
