from __future__ import annotations

import re
from typing import Any

MONTH_CODE = {
    "F": "Jan", "G": "Feb", "H": "Mar", "J": "Apr", "K": "May", "M": "Jun",
    "N": "Jul", "Q": "Aug", "U": "Sep", "V": "Oct", "X": "Nov", "Z": "Dec",
}

_MONTH_CODE_MAP = {
    "F": "January",
    "G": "February",
    "H": "March",
    "J": "April",
    "K": "May",
    "M": "June",
    "N": "July",
    "Q": "August",
    "U": "September",
    "V": "October",
    "X": "November",
    "Z": "December",
}

STANDARD_COLUMNS = [
    "location",
    "commodity",
    "delivery_end",
    "futures_month",
    "futures_price",
    "futures_change",
    "basis",
    "cash_price_bu",
    "cash_price_mt",
]


def parse_number(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None
    s = s.replace("'", ".").replace('-', '.')
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def symbol_to_month(sym: str | None) -> str:
    if not sym:
        return ""
    s = re.sub(r"[^A-Za-z0-9]", "", str(sym))
    m = re.search(r"(\d{1,2})([FGHJKMNQUVXZ])", s, re.IGNORECASE)
    if m:
        year_digit, month_code = m.group(1), m.group(2).upper()
    elif len(s) >= 2 and s[-1].upper() in MONTH_CODE and s[-2].isdigit():
        year_digit, month_code = s[-2], s[-1].upper()
    else:
        return ""

    try:
        year = 2020 + int(year_digit) if len(year_digit) == 1 else 2000 + int(year_digit)
    except Exception:
        return ""

    month_name = MONTH_CODE.get(month_code, "")
    return f"{month_name} {year}" if month_name else ""


def symbol_to_month_extended(sym: str | None) -> str:
    if not sym:
        return ""
    v = symbol_to_month(sym)
    if v:
        return v

    s2 = re.sub(r"[^A-Za-z0-9]", "", str(sym).strip()).lstrip("@")

    m = re.search(r"^(ZC|ZS)([FGHJKMNQUVXZ])(\d{2,4})$", s2, re.IGNORECASE)
    if m:
        mon = m.group(2).upper()
        yr = m.group(3)
        year = int(yr) if len(yr) == 4 else 2000 + int(yr)
        month_name = _MONTH_CODE_MAP.get(mon, "")
        return f"{month_name} {year}" if month_name else ""

    for i, ch in enumerate(s2):
        uc = ch.upper()
        if uc in _MONTH_CODE_MAP:
            m2 = re.match(rf"{re.escape(s2[i])}(\d{{2,4}})", s2[i:])
            if m2:
                yr = m2.group(1)
                year = int(yr) if len(yr) == 4 else 2000 + int(yr)
                return f"{_MONTH_CODE_MAP[uc]} {year}"
            m3 = re.search(r"(\d{1,4})$", s2[:i])
            if m3:
                yr = m3.group(1)
                year = int(yr) if len(yr) == 4 else 2000 + int(yr)
                return f"{_MONTH_CODE_MAP[uc]} {year}"

    return ""
