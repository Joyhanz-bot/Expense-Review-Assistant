"""Deterministic suggestions for management reporting classifications."""

from __future__ import annotations

from datetime import date
from typing import Any

from .utils import normalize_string, parse_date_value, safe_float


# Synthetic demo convention: stays up to 7 nights are treated as short-term.
SHORT_STAY_MAX_NIGHTS = 7


def _mapping(
    level_1: str,
    level_2: str,
    level_3: str,
    reason: str,
) -> dict[str, str]:
    levels = [level_1, level_2, level_3]
    return {
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3,
        "mapping_path": " > ".join(level for level in levels if level),
        "mapping_reason": reason,
    }


def _stay_duration(
    audit: dict[str, Any],
    claim_row: dict[str, Any],
) -> tuple[int | None, str]:
    receipt = audit.get("receipt") or {}
    receipt_nights = safe_float(receipt.get("nights"))
    if receipt_nights is not None and receipt_nights >= 0:
        nights = int(receipt_nights)
        return nights, f"住宿{nights}晚"

    trip_start = parse_date_value(claim_row.get("出差开始"))
    trip_end = parse_date_value(claim_row.get("出差结束"))
    if isinstance(trip_start, date) and isinstance(trip_end, date) and trip_end >= trip_start:
        duration = (trip_end - trip_start).days
        return duration, f"出差时长{duration}天"

    return None, "无法确定住宿晚数或出差时长"


def suggest_reporting_mapping(
    audit: dict[str, Any],
    claim_row: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Return a deterministic reporting suggestion for an approved claim only."""
    if normalize_string(audit.get("final_status")) != "Suggested Pass":
        return None

    claim_row = claim_row or {}
    claimed_type = normalize_string(audit.get("claimed_type"))

    if claimed_type == "Taxi":
        return _mapping(
            "行政费用",
            "差旅费",
            "出租车/打车费",
            "打车费用固定映射",
        )
    if claimed_type == "Overtime Taxi":
        return _mapping(
            "行政费用",
            "差旅费",
            "加班打车费",
            "加班打车费用固定映射",
        )
    if claimed_type == "Meal":
        return _mapping(
            "行政费用",
            "差旅费",
            "出差餐饮费",
            "出差餐饮费用固定映射",
        )
    if claimed_type == "Client Entertainment":
        return _mapping(
            "业务招待费",
            "",
            "",
            "客户招待费用固定映射",
        )
    if claimed_type == "Hotel":
        nights, duration_label = _stay_duration(audit, claim_row)
        if nights is None:
            return None
        if nights <= SHORT_STAY_MAX_NIGHTS:
            return _mapping(
                "行政费用",
                "差旅费",
                "短期出差住宿",
                f"{duration_label}，匹配短期出差住宿规则",
            )
        return _mapping(
            "行政费用",
            "差旅费",
            "长期出差住宿",
            f"{duration_label}，超过{SHORT_STAY_MAX_NIGHTS}晚，匹配长期出差住宿规则",
        )

    return None
