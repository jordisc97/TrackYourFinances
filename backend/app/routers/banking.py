from datetime import datetime
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Account, AccountSource, BankConnection, ConnectionStatus, User
from app.providers.enable_banking import EnableBankingProvider, get_bank_provider
from app.schemas import AuthStartOut, BankConnectionOut, InstitutionOut
from app.services.sync import sync_connection, upsert_balance

router = APIRouter(prefix="/api/banking", tags=["banking"])


def _frontend_url(path_query: str) -> str:
    frontend = get_settings().cors_origins.split(",")[0].strip().rstrip("/")
    return f"{frontend}{path_query}"


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
    settings = get_settings()
    if error:
        if state and state.isdigit():
            connection = db.get(BankConnection, int(state))
            if connection is not None:
                connection.status = ConnectionStatus.error.value
                db.commit()
        detail = error_description or error
        message = "Bank login was cancelled. You can retry from Banks, or import a CSV instead." if error == "access_denied" else f"Bank login failed: {detail}"
        return RedirectResponse(url=_frontend_url(f"/onboarding?bank_status=failed&bank_message={quote(message)}"))
    if not state:
        return RedirectResponse(url=_frontend_url(f"/onboarding?bank_status=failed&bank_message={quote('Missing bank connection state.')}"))
    connection = db.get(BankConnection, int(state))
    if connection is None:
        return RedirectResponse(url=_frontend_url(f"/onboarding?bank_status=failed&bank_message={quote('Bank connection not found.')}"))
    provider = get_bank_provider()
    accounts = []
    if code and not str(code).startswith("mock") and isinstance(provider, EnableBankingProvider) and provider.configured:
        session_response = httpx.post(f"{settings.enable_banking_base_url}/sessions", json={"code": code}, headers=provider._headers(), timeout=30.0)
        if session_response.status_code < 400:
            data = session_response.json()
            connection.session_id = data.get("session_id") or data.get("id")
            expires = (data.get("access") or {}).get("valid_until")
            if expires:
                connection.consent_expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00")).replace(tzinfo=None)
            accounts = [provider._map_account(item) for item in data.get("accounts", []) if isinstance(item, dict)]
            if not accounts and connection.session_id:
                accounts = provider.fetch_accounts(connection.session_id)
        elif connection.session_id:
            accounts = provider.fetch_accounts(connection.session_id)
        else:
            connection.status = ConnectionStatus.error.value
            db.commit()
            return RedirectResponse(url=_frontend_url(f"/onboarding?bank_status=failed&bank_message={quote('Could not finish bank authorization. Try Connect again or import a CSV.')}"))
    elif not code:
        connection.status = ConnectionStatus.error.value
        db.commit()
        return RedirectResponse(url=_frontend_url(f"/onboarding?bank_status=failed&bank_message={quote('Bank login did not return an authorization code. Try again.')}"))
    else:
        result = provider.complete_authorization(code, state, connection.session_id or "")
        connection.session_id = result.session_id
        connection.consent_expires_at = result.consent_expires_at
        accounts = result.accounts
    connection.status = ConnectionStatus.active.value
    connection.last_synced_at = datetime.utcnow()
    for pa in accounts:
        existing = db.query(Account).filter(Account.household_id == connection.household_id, Account.external_id == pa.external_id).first()
        if existing is None:
            account = Account(household_id=connection.household_id, bank_connection_id=connection.id, name=f"{connection.institution_name} {pa.name}", institution=connection.institution_name, currency=pa.currency, account_type=pa.account_type, source=AccountSource.bank.value, external_id=pa.external_id, iban=pa.iban)
            db.add(account)
            db.flush()
            upsert_balance(db, account, pa.balance)
        else:
            existing.bank_connection_id = connection.id
            upsert_balance(db, existing, pa.balance)
    db.commit()
    sync_connection(db, connection, provider)
    return RedirectResponse(url=_frontend_url(f"/?bank_status=connected&bank_message={quote(f'Connected {connection.institution_name}.')}"))


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
