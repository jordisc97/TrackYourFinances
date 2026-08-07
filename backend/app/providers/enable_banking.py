import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import jwt

from app.config import get_settings
from app.providers.base import AuthResult, AuthSession, ProviderAccount, ProviderInstitution, ProviderTransaction
from app.services.tx_enrichment import resolve_counterparty, resolve_merchant

V1_INSTITUTIONS = [
    ProviderInstitution(id="REVOLUT_ES", name="Revolut", country="ES"),
    ProviderInstitution(id="SABADELL_ES", name="Banco Sabadell", country="ES"),
]
PREFERRED_NAMES = ("revolut", "sabadell")


class EnableBankingProvider:
    name = "enable_banking"

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.enable_banking_app_id and self.settings.enable_banking_private_key_path)

    def _private_key(self) -> str:
        return Path(self.settings.enable_banking_private_key_path).read_text(encoding="utf-8")

    def _auth_jwt(self) -> str:
        now = int(time.time())
        payload = {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600}
        return jwt.encode(payload, self._private_key(), algorithm="RS256", headers={"kid": self.settings.enable_banking_app_id, "alg": "RS256"})

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._auth_jwt()}", "Content-Type": "application/json"}

    def list_institutions(self, country: str) -> list[ProviderInstitution]:
        if not self.configured:
            return [i for i in V1_INSTITUTIONS if i.country == country]
        response = httpx.get(f"{self.settings.enable_banking_base_url}/aspsps", params={"country": country}, headers=self._headers(), timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("aspsps", payload if isinstance(payload, list) else [])
        preferred = []
        others = []
        for item in items:
            name = item.get("name", "")
            institution = ProviderInstitution(id=name, name=name, country=item.get("country", country), logo=item.get("logo"))
            if any(p in name.lower() for p in PREFERRED_NAMES):
                preferred.append(institution)
            else:
                others.append(institution)
        if preferred:
            return preferred
        return others[:20] or V1_INSTITUTIONS

    def start_authorization(self, institution_id: str, state: str, psu_type: str = "personal") -> AuthSession:
        if not self.configured:
            session_id = f"mock-{uuid4().hex}"
            redirect = f"{self.settings.enable_banking_redirect_url}?code=mock-code&state={state}"
            return AuthSession(authorization_url=redirect, session_id=session_id)
        account_type = psu_type if psu_type in ("personal", "business") else "personal"
        valid_until = (datetime.now(timezone.utc) + timedelta(days=89)).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {
            "access": {"valid_until": valid_until, "balances": True, "transactions": True},
            "aspsp": {"name": institution_id, "country": self.settings.bank_country},
            "state": state,
            "redirect_url": self.settings.enable_banking_redirect_url,
            "psu_type": account_type,
        }
        response = httpx.post(f"{self.settings.enable_banking_base_url}/auth", json=body, headers=self._headers(), timeout=30.0)
        if response.status_code >= 400:
            raise RuntimeError(f"Enable Banking auth failed ({response.status_code}): {response.text}")
        data = response.json()
        return AuthSession(authorization_url=data["url"], session_id=data.get("authorization_id", ""))

    def complete_authorization(self, code: str | None, state: str, session_id: str) -> AuthResult:
        if not self.configured or (code and str(code).startswith("mock")):
            mock_session = session_id if session_id.startswith("mock-") else f"mock-{uuid4().hex}"
            accounts = [ProviderAccount(external_id=f"{mock_session}-main", name="Main", currency="EUR", iban=None, account_type="checking", balance=0.0)]
            return AuthResult(session_id=mock_session, accounts=accounts, consent_expires_at=datetime.utcnow() + timedelta(days=89))
        response = httpx.post(f"{self.settings.enable_banking_base_url}/sessions", json={"code": code}, headers=self._headers(), timeout=30.0)
        response.raise_for_status()
        data = response.json()
        session = data.get("session_id") or data.get("id")
        accounts = [self._map_account(item) for item in data.get("accounts", []) if isinstance(item, dict)]
        if not accounts and session:
            accounts = self.fetch_accounts(session)
        expires = (data.get("access") or {}).get("valid_until")
        consent_expires = datetime.fromisoformat(expires.replace("Z", "+00:00")).replace(tzinfo=None) if expires else datetime.utcnow() + timedelta(days=89)
        return AuthResult(session_id=session, accounts=accounts, consent_expires_at=consent_expires)

    def _account_balance(self, account_uid: str) -> float | None:
        response = httpx.get(f"{self.settings.enable_banking_base_url}/accounts/{account_uid}/balances", headers=self._headers(), timeout=30.0)
        if response.status_code >= 400:
            return None
        balances = response.json().get("balances") or []
        if not balances:
            return None
        amount_info = balances[0].get("balance_amount") or {}
        return float(amount_info.get("amount", 0))

    def _account_details(self, account_uid: str) -> dict:
        response = httpx.get(f"{self.settings.enable_banking_base_url}/accounts/{account_uid}/details", headers=self._headers(), timeout=30.0)
        if response.status_code >= 400:
            return {"uid": account_uid}
        return response.json()

    def _map_account(self, item: dict) -> ProviderAccount:
        uid = str(item.get("uid") or item.get("id") or "")
        balances = item.get("balances") or []
        amount = 0.0
        if balances:
            balance_amount = balances[0].get("balance_amount") or balances[0].get("amount") or {}
            amount = float(balance_amount.get("amount", 0)) if isinstance(balance_amount, dict) else float(balance_amount or 0)
        elif uid:
            fetched = self._account_balance(uid)
            amount = 0.0 if fetched is None else fetched
        account_id = item.get("account_id")
        iban = account_id.get("iban") if isinstance(account_id, dict) else item.get("iban")
        name = item.get("product") or item.get("details") or item.get("name") or "Account"
        if name.lower().startswith("nombre") and iban:
            name = f"Account …{iban[-4:]}"
        elif iban and name == "Account":
            name = f"Account …{iban[-4:]}"
        return ProviderAccount(
            external_id=uid,
            name=name,
            currency=(item.get("currency") or "EUR"),
            iban=iban,
            account_type="checking",
            balance=amount,
        )

    def fetch_accounts(self, session_id: str) -> list[ProviderAccount]:
        if not self.configured or session_id.startswith("mock-"):
            return [ProviderAccount(external_id=f"{session_id}-main", name="Main", currency="EUR", iban=None, account_type="checking", balance=0.0)]
        response = httpx.get(f"{self.settings.enable_banking_base_url}/sessions/{session_id}", headers=self._headers(), timeout=30.0)
        response.raise_for_status()
        data = response.json()
        account_ids = data.get("accounts") or []
        result = []
        for entry in account_ids:
            uid = entry if isinstance(entry, str) else (entry.get("uid") or entry.get("id"))
            if not uid:
                continue
            details = self._account_details(uid)
            details["uid"] = uid
            result.append(self._map_account(details))
        return result

    def fetch_transactions(self, session_id: str, account_external_id: str, date_from: date | None = None) -> list[ProviderTransaction]:
        if not self.configured or session_id.startswith("mock-"):
            return []
        params = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        url = f"{self.settings.enable_banking_base_url}/accounts/{account_external_id}/transactions"
        response = httpx.get(url, params=params, headers=self._headers(), timeout=60.0)
        if response.status_code == 429:
            time.sleep(45.0)
            response = httpx.get(url, params=params, headers=self._headers(), timeout=60.0)
        if response.status_code == 429:
            return []
        if response.status_code >= 400:
            raise RuntimeError(f"Enable Banking transactions failed ({response.status_code}): {response.text}")
        data = response.json()
        result = []
        for item in data.get("transactions", []):
            booked = item.get("booking_date") or item.get("value_date") or date.today().isoformat()
            value_raw = item.get("value_date")
            amount_info = item.get("transaction_amount") or {}
            amount = abs(float(amount_info.get("amount", 0)))
            indicator = (item.get("credit_debit_indicator") or "").upper()
            remittance = item.get("remittance_information") or []
            description = " ".join(str(x) for x in remittance) if isinstance(remittance, list) and remittance else (item.get("remittance_information_unstructured") or item.get("additional_information") or "")
            # Sabadell remittance often contains "/DB/" as a bank-code token — do not treat that as debit.
            if indicator in ("DBIT", "DEBIT"):
                amount = -amount
            creditor = item.get("creditor") if isinstance(item.get("creditor"), dict) else None
            debtor = item.get("debtor") if isinstance(item.get("debtor"), dict) else None
            creditor_account = item.get("creditor_account") if isinstance(item.get("creditor_account"), dict) else None
            debtor_account = item.get("debtor_account") if isinstance(item.get("debtor_account"), dict) else None
            merchant, location = resolve_merchant(amount, description, creditor, debtor)
            counterparty, counterparty_iban = resolve_counterparty(amount, creditor, debtor, creditor_account, debtor_account)
            balance_info = item.get("balance_after_transaction") or {}
            balance_after = float(balance_info["amount"]) if isinstance(balance_info, dict) and balance_info.get("amount") not in (None, "") else None
            mcc = str(item.get("merchant_category_code") or "").strip() or None
            result.append(
                ProviderTransaction(
                    external_id=str(item.get("entry_reference") or item.get("transaction_id") or uuid4().hex),
                    booked_at=date.fromisoformat(str(booked)[:10]),
                    amount=amount,
                    currency=amount_info.get("currency", "EUR"),
                    description=description,
                    merchant=merchant,
                    counterparty=counterparty,
                    counterparty_iban=counterparty_iban,
                    location=location,
                    mcc=mcc,
                    value_date=date.fromisoformat(str(value_raw)[:10]) if value_raw else None,
                    balance_after=balance_after,
                )
            )
        return result
