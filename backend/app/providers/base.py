from datetime import date, datetime
from typing import Protocol

from dataclasses import dataclass


@dataclass
class ProviderInstitution:
    id: str
    name: str
    country: str
    logo: str | None = None


@dataclass
class ProviderAccount:
    external_id: str
    name: str
    currency: str
    iban: str | None
    account_type: str
    balance: float


@dataclass
class ProviderTransaction:
    external_id: str
    booked_at: date
    amount: float
    currency: str
    description: str
    merchant: str


@dataclass
class AuthSession:
    authorization_url: str
    session_id: str


@dataclass
class AuthResult:
    session_id: str
    accounts: list[ProviderAccount]
    consent_expires_at: datetime | None


class BankProvider(Protocol):
    name: str

    def list_institutions(self, country: str) -> list[ProviderInstitution]: ...
    def start_authorization(self, institution_id: str, state: str) -> AuthSession: ...
    def complete_authorization(self, code: str | None, state: str, session_id: str) -> AuthResult: ...
    def fetch_accounts(self, session_id: str) -> list[ProviderAccount]: ...
    def fetch_transactions(self, session_id: str, account_external_id: str, date_from: date | None = None) -> list[ProviderTransaction]: ...
