from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import BankConnection, ConnectionStatus, User
from app.providers import get_bank_provider
from app.providers.base import BankProvider
from app.providers.gocardless import GoCardlessProvider
from app.schemas import AuthStartOut, BankConnectionOut, InstitutionOut
from app.services.sync import sync_connection

router = APIRouter(prefix="/api/banking", tags=["banking"])


def _banks_redirect(status_value: str, message: str) -> RedirectResponse:
    frontend = get_settings().cors_origins.split(",")[0].strip().rstrip("/")
    return RedirectResponse(url=f"{frontend}/banks?bank_status={status_value}&bank_message={quote(message)}")


def _start_auth(db: Session, connection: BankConnection, provider: BankProvider, psu_type: str = "personal") -> AuthStartOut:
    session = provider.start_authorization(connection.institution_id, state=str(connection.id), psu_type=psu_type)
    connection.session_id = session.session_id
    connection.status = ConnectionStatus.pending.value
    db.commit()
    return AuthStartOut(authorization_url=session.authorization_url, connection_id=connection.id)


def _connection_for_user(db: Session, connection_id: int, household_id: int) -> BankConnection:
    connection = db.query(BankConnection).filter(BankConnection.id == connection_id, BankConnection.household_id == household_id).first()
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return connection


PSU_TYPES = {"personal", "business"}


@router.get("/institutions", response_model=list[InstitutionOut])
def institutions(user: User = Depends(get_current_user)) -> list[InstitutionOut]:
    provider = get_bank_provider()
    return [InstitutionOut(id=i.id, name=i.name, country=i.country, logo=i.logo) for i in provider.list_institutions(get_settings().bank_country)]


@router.get("/connections", response_model=list[BankConnectionOut])
def connections(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BankConnectionOut]:
    rows = (
        db.query(BankConnection)
        .filter(BankConnection.household_id == user.household_id)
        .order_by(BankConnection.created_at.desc())
        .all()
    )
    return [
        BankConnectionOut(
            id=row.id,
            provider=row.provider,
            institution_id=row.institution_id,
            institution_name=row.institution_name,
            status=row.status,
            consent_expires_at=row.consent_expires_at,
            last_synced_at=row.last_synced_at,
            created_at=row.created_at,
            is_mock=(row.session_id or "").startswith("mock-"),
        )
        for row in rows
    ]


@router.post("/connect/{institution_id}", response_model=AuthStartOut)
def connect(institution_id: str, psu_type: str = "personal", user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthStartOut:
    account_type = psu_type if psu_type in PSU_TYPES else "personal"
    provider = get_bank_provider()
    institutions = {i.id: i for i in provider.list_institutions(get_settings().bank_country)}
    institution = institutions.get(institution_id)
    if institution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
    connection = BankConnection(household_id=user.household_id, provider=provider.name, institution_id=institution.id, institution_name=institution.name, status=ConnectionStatus.pending.value)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    try:
        return _start_auth(db, connection, provider, account_type)
    except RuntimeError as exc:
        connection.status = ConnectionStatus.error.value
        db.commit()
        detail = str(exc)
        if "REDIRECT_URI_NOT_ALLOWED" in detail or "Redirect URI not allowed" in detail:
            redirect = get_settings().enable_banking_redirect_url
            detail = f"Enable Banking rejected the redirect URL. In the Control Panel, add this exact Redirect URL, then retry: {redirect}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


@router.get("/callback")
def callback(
    code: str | None = None,
    state: str | None = None,
    ref: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    connection_ref = state or ref
    if error:
        if connection_ref and connection_ref.isdigit():
            connection = db.get(BankConnection, int(connection_ref))
            if connection is not None:
                connection.status = ConnectionStatus.error.value
                db.commit()
        detail = error_description or error
        message = f"Bank login was cancelled ({detail}). Retry from Banks, or import a CSV." if error == "access_denied" else f"Bank login failed: {detail}"
        return _banks_redirect("failed", message)
    if not connection_ref or not connection_ref.isdigit():
        return _banks_redirect("failed", "Missing bank connection state.")
    connection = db.get(BankConnection, int(connection_ref))
    if connection is None:
        return _banks_redirect("failed", "Bank connection not found.")
    provider = get_bank_provider()
    is_gocardless = connection.provider == GoCardlessProvider.name or isinstance(provider, GoCardlessProvider)
    if not is_gocardless and not code:
        connection.status = ConnectionStatus.error.value
        db.commit()
        return _banks_redirect("failed", "Bank login did not return an authorization code. Try again.")
    result = provider.complete_authorization(code, connection_ref, connection.session_id or "")
    connection.session_id = result.session_id
    connection.consent_expires_at = result.consent_expires_at
    connection.status = ConnectionStatus.active.value
    db.commit()
    sync_connection(db, connection, provider)
    return _banks_redirect("connected", f"Connected {connection.institution_name}.")


@router.post("/connections/{connection_id}/sync")
def sync(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    connection = _connection_for_user(db, connection_id, user.household_id)
    imported = sync_connection(db, connection, get_bank_provider())
    return {"imported": imported, "status": connection.status}


@router.post("/connections/{connection_id}/reconnect", response_model=AuthStartOut)
def reconnect(connection_id: int, psu_type: str = "personal", user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthStartOut:
    account_type = psu_type if psu_type in PSU_TYPES else "personal"
    return _start_auth(db, _connection_for_user(db, connection_id, user.household_id), get_bank_provider(), account_type)
