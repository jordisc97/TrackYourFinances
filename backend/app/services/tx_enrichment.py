import re

CARD_MARKER = "COMPRA TARJ."
CARD_TAIL = re.compile(r"(?:COMPRA\s+TARJ\.?\s*)?(?:\d{4}X+\d{4}\s+)?(.+)$", re.IGNORECASE)
PLACE_TAIL = re.compile(r"^(?P<merchant>.+)-(?P<place>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .']{1,40})$")


def _clean(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def parse_card_merchant_location(description: str) -> tuple[str, str]:
    text = _clean(description)
    if not text:
        return "", ""
    if CARD_MARKER.lower() not in text.lower() and "compra tarj" not in text.lower():
        return "", ""
    match = CARD_TAIL.search(text)
    remainder = _clean(match.group(1) if match else text)
    place_match = PLACE_TAIL.match(remainder)
    if place_match:
        return _clean(place_match.group("merchant")), _clean(place_match.group("place"))
    return remainder, ""


def party_name(party: dict | None) -> str:
    if not isinstance(party, dict):
        return ""
    return _clean(party.get("name"))


def party_iban(account: dict | None) -> str:
    if not isinstance(account, dict):
        return ""
    return _clean(account.get("iban"))


def resolve_counterparty(amount: float, creditor: dict | None, debtor: dict | None, creditor_account: dict | None, debtor_account: dict | None) -> tuple[str, str]:
    # Debits: money leaves to creditor; credits: money arrives from debtor.
    if amount < 0:
        return party_name(creditor), party_iban(creditor_account)
    return party_name(debtor) or party_name(creditor), party_iban(debtor_account) or party_iban(creditor_account)


def resolve_merchant(amount: float, description: str, creditor: dict | None, debtor: dict | None) -> tuple[str, str]:
    counterparty = party_name(creditor) if amount < 0 else (party_name(debtor) or party_name(creditor))
    card_merchant, location = parse_card_merchant_location(description)
    if card_merchant:
        return card_merchant, location
    if counterparty:
        return counterparty, ""
    return _clean(description)[:255], ""
