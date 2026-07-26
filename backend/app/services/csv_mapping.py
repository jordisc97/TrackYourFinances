import re
import unicodedata
from dataclasses import dataclass

from app.services.deepseek import map_csv_columns_with_deepseek

SCHEMA_FIELDS = ("booked_at", "amount", "raw_description", "merchant", "external_id")
REQUIRED_FIELDS = ("booked_at", "amount")
SAMPLE_ROW_LIMIT = 3
MAPPING_SOURCE_REGEX = "regex"
MAPPING_SOURCE_LLM = "llm"
MAPPING_SOURCE_HYBRID = "hybrid"

# Normalized header patterns (accents/spaces stripped) per schema field — bank-agnostic aliases.
FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "booked_at": (
        re.compile(r"^(bookedat|bookingdate|valuedate|transactiondate|completeddate|operationdate|fechaoperacion|fechavalor|fechacontable|fecha|date)$"),
        re.compile(r"fecha(operacion|valor|contable)?|(booking|value|transaction|completed|operation)date"),
    ),
    "amount": (
        re.compile(r"^(amount|importe|transactionamount|monto|suma|cantidad|value|quantidade|betrag)$"),
        re.compile(r"amount|importe|monto|betrag|cantidad|suma"),
    ),
    "raw_description": (
        re.compile(r"^(rawdescription|description|concepto|narration|details|memo|notes|remittance|info|descripcion|beschreibung)$"),
        re.compile(r"description|concepto|narration|remittance|descripcion|beschreibung"),
    ),
    "merchant": (
        re.compile(r"^(merchant|counterparty|payee|beneficiary|beneficiario|comercio|establecimiento|counterpartname|creditor|debtor)$"),
        re.compile(r"merchant|counterparty|payee|beneficiar|comercio|creditor|debtor|establecimiento"),
    ),
    "external_id": (
        re.compile(r"^(externalid|transactionid|bookingid|txid|id|uuid|referenceid)$"),
        re.compile(r"externalid|transactionid|bookingid|^id$"),
    ),
}


@dataclass(frozen=True)
class ColumnMapping:
    booked_at: str | None
    amount: str | None
    raw_description: str | None
    merchant: str | None
    external_id: str | None
    source: str

    def header_for(self, field: str) -> str | None:
        return getattr(self, field)

    def missing_required(self) -> list[str]:
        return [field for field in REQUIRED_FIELDS if not self.header_for(field)]


def normalize_header(header: str) -> str:
    stripped = unicodedata.normalize("NFKD", header.strip())
    ascii_only = "".join(char for char in stripped if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", ascii_only.lower())


def _score_header(field: str, header: str) -> int:
    normalized = normalize_header(header)
    if not normalized:
        return 0
    exact, fuzzy = FIELD_PATTERNS[field]
    if exact.match(normalized):
        return 100
    if fuzzy.search(normalized):
        return 50
    return 0


def map_columns_with_regex(headers: list[str]) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {field: None for field in SCHEMA_FIELDS}
    used: set[str] = set()
    # Strongest match wins; each CSV header maps to at most one schema field.
    candidates = [(field, header, _score_header(field, header)) for field in SCHEMA_FIELDS for header in headers]
    for field, header, score in sorted(candidates, key=lambda item: item[2], reverse=True):
        if score <= 0 or mapping[field] is not None or header in used:
            continue
        mapping[field], used = header, used | {header}
    return mapping


def _merge_mappings(primary: dict[str, str | None], fallback: dict[str, str | None]) -> dict[str, str | None]:
    return {field: primary.get(field) or fallback.get(field) for field in SCHEMA_FIELDS}


def _mapping_source(regex_map: dict[str, str | None], final_map: dict[str, str | None]) -> str:
    used_llm = any(final_map[field] and final_map[field] != regex_map.get(field) for field in SCHEMA_FIELDS)
    used_regex = any(regex_map.get(field) for field in SCHEMA_FIELDS)
    if used_llm and used_regex:
        return MAPPING_SOURCE_HYBRID
    return MAPPING_SOURCE_LLM if used_llm else MAPPING_SOURCE_REGEX


def _to_column_mapping(raw: dict[str, str | None], source: str) -> ColumnMapping:
    return ColumnMapping(booked_at=raw.get("booked_at"), amount=raw.get("amount"), raw_description=raw.get("raw_description"), merchant=raw.get("merchant"), external_id=raw.get("external_id"), source=source)


def resolve_column_mapping(headers: list[str], sample_rows: list[dict[str, str]] | None = None) -> ColumnMapping:
    cleaned_headers = [header for header in headers if header is not None and str(header).strip()]
    regex_map = map_columns_with_regex(cleaned_headers)
    if all(regex_map.get(field) for field in REQUIRED_FIELDS):
        return _to_column_mapping(regex_map, MAPPING_SOURCE_REGEX)
    llm_map = map_csv_columns_with_deepseek(cleaned_headers, sample_rows or []) or {}
    # Only accept LLM headers that actually exist in the file.
    llm_validated = {field: (header if header in cleaned_headers else None) for field, header in llm_map.items()}
    final_map = _merge_mappings(regex_map, llm_validated)
    return _to_column_mapping(final_map, _mapping_source(regex_map, final_map))


def pick_mapped(row: dict, mapping: ColumnMapping, field: str, default: str = "") -> str:
    header = mapping.header_for(field)
    if not header or header not in row or row[header] in (None, ""):
        return default
    return str(row[header]).strip()
