from __future__ import annotations

import math
import numbers
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

import pandas as pd

from app.models.source import Source
from app.services.source_orchestration import fetch_source_once
from app.services.source_registry import SourceFetchTarget, get_adapter
from app.services.us_source_candidates import load_us_source_candidates


MAX_PREVIEW_ROWS = 8
MAX_PREVIEW_COLUMNS = 12
MAX_CELL_CHARACTERS = 200
MIN_REQUIRED_COVERAGE = 0.8

_REQUIRED_FIELD_ALIASES = {
    "location": {"location"},
    "commodity": {"commodity", "name"},
    "delivery": {"delivery", "delivery start", "delivery end"},
    "price": {"bushel cash price", "mt cash price", "cash price", "price", "basis"},
}
_SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(?:password|passwd|secret|token|authorization|cookie|api.?key|email|phone)",
    re.IGNORECASE,
)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SourceProbeEligibilityError(ValueError):
    pass


def probe_source(source: Source) -> dict[str, Any]:
    adapter, approved_url = _validate_probe_eligibility(source)
    timeout_seconds = max(15, int(source.timeout_seconds or adapter.default_timeout_seconds))
    dataframe = fetch_source_once(
        adapter.key,
        timeout_seconds=timeout_seconds,
        target=SourceFetchTarget(name=source.name, url=approved_url),
    )
    return _summarize_probe(dataframe, timeout_seconds=timeout_seconds)


def _validate_probe_eligibility(source: Source):
    if source.is_active:
        raise SourceProbeEligibilityError("only inactive sources can be probed")
    if (source.collection_status or "").strip().lower() != "candidate":
        raise SourceProbeEligibilityError("only candidate sources can be probed")
    if source.source_type != "automated" or not source.adapter_key:
        raise SourceProbeEligibilityError("only automated sources with an adapter can be probed")

    try:
        adapter = get_adapter(source.adapter_key)
    except KeyError as exc:
        raise SourceProbeEligibilityError(str(exc)) from exc
    if not adapter.requires_target:
        raise SourceProbeEligibilityError("only target-aware adapters can be probed")

    url = (source.url or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SourceProbeEligibilityError("source must have a valid HTTPS URL without embedded credentials")

    approved = any(
        candidate.url == url and candidate.adapter_key == adapter.key
        for candidate in load_us_source_candidates()
    )
    if not approved:
        raise SourceProbeEligibilityError("source URL and adapter do not match the approved US candidate config")
    return adapter, url


def _summarize_probe(dataframe: pd.DataFrame, *, timeout_seconds: int) -> dict[str, Any]:
    raw_row_count = int(len(dataframe.index))
    original_columns = [str(column) for column in dataframe.columns]
    safe_column_positions = [
        index
        for index, column in enumerate(original_columns)
        if not _SENSITIVE_COLUMN_PATTERN.search(column)
    ]
    safe_columns = [_sanitize_text(original_columns[index], limit=100) for index in safe_column_positions]

    normalized_columns = [_normalize_column(column) for column in original_columns]
    coverage: dict[str, dict[str, Any]] = {}
    fail_reasons: list[str] = []
    pass_reasons = [
        "stored URL matched the approved US candidate config",
        "one isolated fetch attempt completed",
    ]

    if raw_row_count == 0:
        fail_reasons.append("source returned no rows")

    for field, aliases in _REQUIRED_FIELD_ALIASES.items():
        positions = [index for index, column in enumerate(normalized_columns) if column in aliases]
        present_count = _count_rows_with_value(dataframe, positions)
        ratio = (present_count / raw_row_count) if raw_row_count else 0.0
        matched_columns = [original_columns[index] for index in positions]
        coverage[field] = {
            "matched_columns": matched_columns,
            "present_rows": present_count,
            "total_rows": raw_row_count,
            "ratio": round(ratio, 4),
        }
        if not positions:
            fail_reasons.append(f"no recognized {field} column")
        elif ratio < MIN_REQUIRED_COVERAGE:
            fail_reasons.append(
                f"{field} coverage {ratio * 100:.1f}% is below {MIN_REQUIRED_COVERAGE * 100:.0f}%"
            )
        else:
            pass_reasons.append(f"{field} coverage is {ratio * 100:.1f}%")

    preview_positions = safe_column_positions[:MAX_PREVIEW_COLUMNS]
    preview = []
    for row_number in range(min(raw_row_count, MAX_PREVIEW_ROWS)):
        preview.append(
            {
                _sanitize_text(original_columns[position], limit=100): _sanitize_value(
                    dataframe.iloc[row_number, position]
                )
                for position in preview_positions
            }
        )

    return {
        "passed": not fail_reasons,
        "attempts": 1,
        "timeout_seconds": timeout_seconds,
        "raw_row_count": raw_row_count,
        "column_count": len(original_columns),
        "columns": safe_columns,
        "required_field_coverage": coverage,
        "commodities": _unique_values(dataframe, normalized_columns, {"commodity", "name"}),
        "locations": _unique_values(dataframe, normalized_columns, {"location"}),
        "pass_reasons": pass_reasons,
        "fail_reasons": fail_reasons,
        "preview": preview,
        "preview_limit": MAX_PREVIEW_ROWS,
        "preview_truncated": raw_row_count > MAX_PREVIEW_ROWS or len(safe_column_positions) > MAX_PREVIEW_COLUMNS,
        "persisted": False,
    }


def _normalize_column(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _count_rows_with_value(dataframe: pd.DataFrame, positions: list[int]) -> int:
    if not positions:
        return 0
    return sum(
        1
        for row_number in range(len(dataframe.index))
        if any(_has_value(dataframe.iloc[row_number, position]) for position in positions)
    )


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _unique_values(
    dataframe: pd.DataFrame,
    normalized_columns: list[str],
    aliases: set[str],
) -> list[str]:
    positions = [index for index, column in enumerate(normalized_columns) if column in aliases]
    values: set[str] = set()
    for row_number in range(len(dataframe.index)):
        for position in positions:
            value = dataframe.iloc[row_number, position]
            if _has_value(value):
                values.add(_sanitize_text(str(value), limit=100))
    return sorted(values, key=str.casefold)[:50]


def _sanitize_value(value: Any) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        numeric_value = float(value)
        return numeric_value if math.isfinite(numeric_value) else None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return _sanitize_text(str(value), limit=MAX_CELL_CHARACTERS)


def _sanitize_text(value: str, *, limit: int) -> str:
    cleaned = _CONTROL_CHARACTERS.sub("", value).replace("<", "‹").replace(">", "›").strip()
    return cleaned[:limit]
