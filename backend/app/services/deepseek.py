import re

import httpx

from app.config import get_settings
from app.seed import EXPENSE_CATEGORY_NAMES

CATEGORY_JSON_RE = re.compile(r'"category"\s*:\s*"([^"]+)"')
CSV_SCHEMA_FIELDS = ("booked_at", "amount", "raw_description", "merchant", "external_id")
DEEPSEEK_TIMEOUT_SECONDS = 20.0
BENCHMARK_TIMEOUT_SECONDS = 45.0
LLM_RULE_PRIORITY = 80
CSV_MAPPING_SAMPLE_LIMIT = 3


def _message_content(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    return str(message.get("content") or "") if isinstance(message, dict) else ""


def _chat_completion(messages: list[dict[str, str]], timeout_seconds: float = DEEPSEEK_TIMEOUT_SECONDS) -> str | None:
    settings = get_settings()
    if not settings.deepseek_api:
        return None
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.deepseek_api}", "Content-Type": "application/json"}
    body = {"model": settings.deepseek_model, "messages": messages, "temperature": 0}
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, headers=headers, json=body)
    if response.status_code != 200:
        return None
    payload = response.json()
    return _message_content(payload) if isinstance(payload, dict) else None


def classify_with_deepseek(description: str, merchant: str, amount: float, currency: str) -> str | None:
    allowed = ", ".join(EXPENSE_CATEGORY_NAMES)
    messages = [
        {
            "role": "system",
            "content": (
                "Classify a bank transaction into exactly one expense category. "
                'Reply with JSON only: {"category":"<name>"}. '
                f"Allowed names: {allowed}. "
                "Groceries = supermarket/home food; Dining & Takeaway = restaurants/delivery/cafes/bars."
            ),
        },
        {"role": "user", "content": f"description={description!r}; merchant={merchant!r}; amount={amount}; currency={currency}"},
    ]
    content = _chat_completion(messages)
    if not content:
        return None
    match = CATEGORY_JSON_RE.search(content)
    name = match.group(1).strip() if match else ""
    return name if name in EXPENSE_CATEGORY_NAMES else None


def benchmark_category_spend(location: str, monthly_income: float, categories: list[str]) -> dict[str, float] | None:
    allowed = ", ".join(categories)
    messages = [
        {
            "role": "system",
            "content": (
                "You estimate typical monthly household spending for an average person. "
                "Use public cost-of-living and Eurostat-style consumption patterns for the given city/country. "
                "Scale amounts to the given net monthly salary. "
                "Reply with JSON only: keys are exact category names, values are monthly euros as numbers. "
                f"Required keys: {allowed}. No extra keys."
            ),
        },
        {
            "role": "user",
            "content": (
                f"location={location!r}; net_monthly_income_eur={monthly_income}; "
                "Return typical monthly spend in EUR for each category for an average person at this income."
            ),
        },
    ]
    content = _chat_completion(messages, timeout_seconds=BENCHMARK_TIMEOUT_SECONDS)
    if not content:
        return None
    result: dict[str, float] = {}
    for name in categories:
        match = re.search(rf'"{re.escape(name)}"\s*:\s*(-?\d+(?:\.\d+)?)', content)
        if match:
            result[name] = max(float(match.group(1)), 0.0)
    return result if len(result) >= max(1, len(categories) // 2) else None


def map_csv_columns_with_deepseek(headers: list[str], sample_rows: list[dict[str, str]]) -> dict[str, str | None] | None:
    fields = ", ".join(CSV_SCHEMA_FIELDS)
    messages = [
        {
            "role": "system",
            "content": (
                "Map bank CSV column headers to our transaction schema. "
                f"Schema fields: {fields}. "
                "Reply with JSON only using those keys; value is an exact header string from the file or null. "
                "Required fields are booked_at and amount."
            ),
        },
        {"role": "user", "content": f"headers={headers!r}; sample_rows={sample_rows[:CSV_MAPPING_SAMPLE_LIMIT]!r}"},
    ]
    content = _chat_completion(messages)
    if not content:
        return None
    header_set = set(headers)
    mapping: dict[str, str | None] = {field: None for field in CSV_SCHEMA_FIELDS}
    for field in CSV_SCHEMA_FIELDS:
        match = re.search(rf'"{field}"\s*:\s*(?:"([^"]*)"|null)', content)
        if not match:
            continue
        value = match.group(1)
        mapping[field] = value if value in header_set else None
    return mapping
