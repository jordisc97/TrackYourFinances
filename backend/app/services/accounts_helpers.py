import re

from app.models import Account

MIN_IBAN_MATCH_LEN = 8
MIN_NAME_MATCH_LEN = 4
INCOME_NODE_ID = "income"
EXPENSES_NODE_ID = "expenses"
NODE_KIND_INCOME = "income"
NODE_KIND_ACCOUNT = "account"
NODE_KIND_EXPENSES = "expenses"
EDGE_KIND_INCOME = "income"
EDGE_KIND_SPEND = "spend"
EDGE_KIND_TRANSFER = "transfer"


def normalize_iban(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", "", value).upper()
    return cleaned or None


def account_node_id(account_id: int) -> str:
    return f"account-{account_id}"


def mask_iban(iban: str | None) -> str:
    if not iban:
        return ""
    if len(iban) <= 4:
        return iban
    return f"…{iban[-4:]}"


def tx_haystack(description: str, merchant: str) -> str:
    return f"{description} {merchant}".upper().replace(" ", "")


def tx_haystack_lower(description: str, merchant: str) -> str:
    return f"{description} {merchant}".lower()


def match_own_account_id(accounts: list[Account], description: str, merchant: str, exclude_account_id: int | None = None) -> int | None:
    compact = tx_haystack(description, merchant)
    lower = tx_haystack_lower(description, merchant)
    for account in accounts:
        if exclude_account_id is not None and account.id == exclude_account_id:
            continue
        iban = normalize_iban(account.iban)
        if iban and len(iban) >= MIN_IBAN_MATCH_LEN and iban in compact:
            return account.id
        name = (account.name or "").strip().lower()
        if len(name) >= MIN_NAME_MATCH_LEN and name in lower:
            return account.id
    return None


def matches_own_account(accounts: list[Account], description: str, merchant: str, exclude_account_id: int | None = None) -> bool:
    return match_own_account_id(accounts, description, merchant, exclude_account_id) is not None
