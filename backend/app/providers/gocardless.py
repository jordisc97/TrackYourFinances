import time
from datetime import date, datetime, timedelta
from uuid import uuid4

import httpx

from app.config import get_settings
from app.providers.base import AuthResult, AuthSession, ProviderAccount, ProviderInstitution, ProviderTransaction

MOCK_INSTITUTIONS = [
    ProviderInstitution(id="SANDBOXFINANCE_SFIN0000", name="Sandbox Finance", country="ES"),
    ProviderInstitution(id="REVOLUT_REVOES22", name="Revolut", country="ES"),
]
TOKEN_EXPIRY_BUFFER_SECONDS = 30
CONSENT_DAYS = 89
HTTP_TIMEOUT = 30.0
TX_TIMEOUT = 60.0


class GoCardlessProvider:
    name = "gocardless"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.token: str | None = None
        self.token_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.settings.gc_secret_id and self.settings.gc_secret_key)

    def _authenticate(self) -> str:
        response = httpx.post(
            f"{self.settings.gc_base_url}/token/new/",
            json={"secret_id": self.settings.gc_secret_id, "secret_key": self.settings.gc_secret_key},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access"]
        self.token_expires_at = time.time() + data["access_expires"] - TOKEN_EXPIRY_BUFFER_SECONDS
        return self.token

    def _headers(self) -> dict[str, str]:
        if not self.token or time.time() > self.token_expires_at:
            self._authenticate()
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def list_institutions(self, country: str) -> list[ProviderInstitution]:
        if not self.configured:
            return [i for i in MOCK_INSTITUTIONS if i.country == country] or MOCK_INSTITUTIONS
        response = httpx.get(f"{self.settings.gc_base_url}/institutions/", headers=self._headers(), params={"country": country}, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        items = response.json()
        return [ProviderInstitution(id=item["id"], name=item.get("name", item["id"]), country=country, logo=item.get("logo")) for item in items]

    def start_authorization(self, institution_id: str, state: str) -> AuthSession:
        if not self.configured:
            session_id = f"mock-{uuid4().hex}"
            redirect = f"{self.settings.gc_redirect_url}?ref={state}"
            return AuthSession(authorization_url=redirect, session_id=session_id)
        body = {"redirect": self.settings.gc_redirect_url, "institution_id": institution_id, "reference": state, "user_language": "EN"}
        response = httpx.post(f"{self.settings.gc_base_url}/requisitions/", headers=self._headers(), json=body, timeout=HTTP_TIMEOUT)
        if response.status_code >= 400:
            raise RuntimeError(f"GoCardless requisition failed ({response.status_code}): {response.text}")
        data = response.json()
        return AuthSession(authorization_url=data["link"], session_id=data["id"])

    def complete_authorization(self, code: str | None, state: str, session_id: str) -> AuthResult:
        if not self.configured or session_id.startswith("mock-"):
            accounts = [ProviderAccount(external_id=f"{session_id}-main", name="Main", currency="EUR", iban=None, account_type="checking", balance=0.0)]
            return AuthResult(session_id=session_id, accounts=accounts, consent_expires_at=datetime.utcnow() + timedelta(days=CONSENT_DAYS))
        response = httpx.get(f"{self.settings.gc_base_url}/requisitions/{session_id}/", headers=self._headers(), timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        account_ids = data.get("accounts") or []
        if not account_ids:
            raise RuntimeError("GoCardless requisition has no linked accounts yet. Complete bank consent and retry.")
        accounts = self.fetch_accounts(session_id)
        return AuthResult(session_id=session_id, accounts=accounts, consent_expires_at=datetime.utcnow() + timedelta(days=CONSENT_DAYS))

    def _account_balance(self, account_id: str) -> float:
        response = httpx.get(f"{self.settings.gc_base_url}/accounts/{account_id}/balances/", headers=self._headers(), timeout=HTTP_TIMEOUT)
        if response.status_code >= 400:
            return 0.0
        balances = response.json().get("balances") or []
        if not balances:
            return 0.0
        amount_info = balances[0].get("balanceAmount") or {}
        return float(amount_info.get("amount", 0))

    def _map_account(self, account_id: str, details: dict) -> ProviderAccount:
        account = details.get("account") or details
        iban = account.get("iban")
        name = account.get("name") or account.get("product") or account.get("ownerName") or "Account"
        if iban and name == "Account":
            name = f"Account …{iban[-4:]}"
        currency = account.get("currency") or "EUR"
        return ProviderAccount(external_id=account_id, name=name, currency=currency, iban=iban, account_type="checking", balance=self._account_balance(account_id))

    def fetch_accounts(self, session_id: str) -> list[ProviderAccount]:
        if not self.configured or session_id.startswith("mock-"):
            return [ProviderAccount(external_id=f"{session_id}-main", name="Main", currency="EUR", iban=None, account_type="checking", balance=0.0)]
        response = httpx.get(f"{self.settings.gc_base_url}/requisitions/{session_id}/", headers=self._headers(), timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        account_ids = response.json().get("accounts") or []
        result = []
        for account_id in account_ids:
            details_resp = httpx.get(f"{self.settings.gc_base_url}/accounts/{account_id}/details/", headers=self._headers(), timeout=HTTP_TIMEOUT)
            details = details_resp.json() if details_resp.status_code < 400 else {"account": {}}
            result.append(self._map_account(account_id, details))
        return result

    def _map_transaction(self, item: dict) -> ProviderTransaction:
        amount_info = item.get("transactionAmount") or {}
        amount = float(amount_info.get("amount", 0))
        booked = item.get("bookingDate") or item.get("valueDate") or date.today().isoformat()
        description = item.get("remittanceInformationUnstructured") or ""
        if not description:
            remittance = item.get("remittanceInformationUnstructuredArray") or []
            description = " ".join(str(x) for x in remittance) if remittance else ""
        merchant = item.get("creditorName") or item.get("debtorName") or ""
        external_id = str(item.get("transactionId") or item.get("internalTransactionId") or item.get("entryReference") or uuid4().hex)
        return ProviderTransaction(external_id=external_id, booked_at=date.fromisoformat(str(booked)[:10]), amount=amount, currency=amount_info.get("currency", "EUR"), description=description, merchant=merchant)

    def fetch_transactions(self, session_id: str, account_external_id: str, date_from: date | None = None) -> list[ProviderTransaction]:
        if not self.configured or session_id.startswith("mock-"):
            return []
        params = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        response = httpx.get(f"{self.settings.gc_base_url}/accounts/{account_external_id}/transactions/", headers=self._headers(), params=params, timeout=TX_TIMEOUT)
        response.raise_for_status()
        transactions = response.json().get("transactions") or {}
        result = []
        for status_key in ("booked", "pending"):
            for item in transactions.get(status_key, []):
                result.append(self._map_transaction(item))
        return result
