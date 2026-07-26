import re

import httpx

from app.config import get_settings
from app.seed import EXPENSE_CATEGORY_NAMES

CATEGORY_JSON_RE = re.compile(r'"category"\s*:\s*"([^"]+)"')
CSV_SCHEMA_FIELDS = ("booked_at", "amount", "raw_description", "merchant", "external_id")
DEEPSEEK_TIMEOUT_SECONDS = 20.0
LLM_RULE_PRIORITY = 80
CSV_MAPPING_SAMPLE_LIMIT = 3


def _build_prompt(description: str, merchant: str, amount: float, currency: str) -> list[dict[str, str]]:
    allowed = ", ".join(EXPENSE_CATEGORY_NAMES)
    system = (
        "Classify a bank transaction into exactly one expense category. "
        "Reply with JSON only: {\"category\":\"<name>\"}. "
        f"Allowed names: {allowed}. "
        "Groceries = supermarket/home food; Dining & Takeaway = restaurants/delivery/cafes/bars. "
        "Housing = rent/mortgage/home insurance/maintenance; One-off Large Purchases = renovations/big-ticket furniture/appliances; "
        "Electronics & Home Goods = gadgets/appliances/tech accessories of ordinary size."
    )
    user = f"description={description!r}; merchant={merchant!r}; amount={amount}; currency={currency}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_csv_mapping_prompt(headers: list[str], sample_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    fields = ", ".join(CSV_SCHEMA_FIELDS)
    system = (
        "Map bank CSV column headers to our transaction schema. "
        f"Schema fields: {fields}. "
        "booked_at=transaction date; amount=signed money value; raw_description=memo/concept; "
        "merchant=counterparty/payee; external_id=bank transaction id. "
        "Reply with JSON only using those keys; value is an exact header string from the file or null. "
        "Each header may map to at most one field; required fields are booked_at and amount."
    )
    samples = sample_rows[:CSV_MAPPING_SAMPLE_LIMIT]
    user = f"headers={headers!r}; sample_rows={samples!r}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_category_name(content: str) -> str | None:
    match = CATEGORY_JSON_RE.search(content)
    if not match:
        return None
    name = match.group(1).strip()
    return name if name in EXPENSE_CATEGORY_NAMES else None


def _parse_csv_column_mapping(content: str, headers: list[str]) -> dict[str, str | None]:
    header_set = set(headers)
    mapping: dict[str, str | None] = {field: None for field in CSV_SCHEMA_FIELDS}
    for field in CSV_SCHEMA_FIELDS:
        match = re.search(rf'"{field}"\s*:\s*(?:"([^"]*)"|null)', content)
        if not match:
            continue
        value = match.group(1)
        mapping[field] = value if value in header_set else None
    return mapping


def _message_content(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


def _chat_completion(messages: list[dict[str, str]]) -> str | None:
    settings = get_settings()
    if not settings.deepseek_api:
        return None
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.deepseek_api}", "Content-Type": "application/json"}
    body = {"model": settings.deepseek_model, "messages": messages, "temperature": 0}
    with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS) as client:
        response = client.post(url, headers=headers, json=body)
    if response.status_code != 200:
        return None
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    return _message_content(payload) or None


def classify_with_deepseek(description: str, merchant: str, amount: float, currency: str) -> str | None:
    content = _chat_completion(_build_prompt(description, merchant, amount, currency))
    return _parse_category_name(content) if content else None


def map_csv_columns_with_deepseek(headers: list[str], sample_rows: list[dict[str, str]]) -> dict[str, str | None] | None:
    content = _chat_completion(_build_csv_mapping_prompt(headers, sample_rows))
    return _parse_csv_column_mapping(content, headers) if content else None
