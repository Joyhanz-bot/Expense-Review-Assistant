from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
SAMPLE_TEMPLATE_PATH = SAMPLE_DATA_DIR / "expense_template.xlsx"
SAMPLE_POLICY_PATH = SAMPLE_DATA_DIR / "Mock_Travel_Expense_Policy.pdf"
SAMPLE_RECEIPTS_DIR = SAMPLE_DATA_DIR / "receipts"

SEMANTIC_CATEGORY_COMPATIBILITY = {
    "Taxi": {"Taxi", "Transportation"},
    "Overtime Taxi": {"Taxi", "Transportation"},
    "Hotel": {"Hotel"},
    "Meal": {"Meal"},
    "Client Entertainment": {"Client Entertainment"},
    "Miscellaneous": {"Other", "Mixed Expense"},
}


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    return "" if text.lower() == "nan" else text


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def parse_date_value(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()

    text = normalize_string(value)
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def find_expense_id(text: Any) -> str:
    match = re.search(r"(E\d{3})", normalize_string(text), re.IGNORECASE)
    return match.group(1).upper() if match else ""


def clamp_confidence(value: Any) -> float:
    number = safe_float(value)
    if number is None:
        return 0.0
    return max(0.0, min(1.0, number))


def list_sample_receipt_paths() -> list[Path]:
    return sorted(SAMPLE_RECEIPTS_DIR.glob("*.pdf"))


def semantic_mode_label(result: dict[str, Any] | None) -> str:
    if not result:
        return "Not analyzed"
    provider = normalize_string(result.get("provider"))
    if provider == "llm":
        return "LLM-assisted"
    if provider == "fallback":
        return "Fallback demo"
    return "Not analyzed"


def is_semantic_category_compatible(claimed_type: str, semantic_category: str) -> bool:
    claimed = normalize_string(claimed_type)
    category = normalize_string(semantic_category)
    if not claimed or not category:
        return True
    allowed = SEMANTIC_CATEGORY_COMPATIBILITY.get(claimed)
    if not allowed:
        return True
    return category in allowed


def summarize_rule_findings(rule_results: list[dict[str, Any]]) -> str:
    findings = [
        f"{result['rule_name']}: {result['message']}"
        for result in rule_results
        if result.get("status") != "pass"
    ]
    return " | ".join(findings) if findings else "No deterministic exception detected."


def determine_final_status(
    rule_results: list[dict[str, Any]],
    claimed_type: str,
    semantic_result: dict[str, Any] | None,
) -> tuple[str, str]:
    fail_messages = [
        f"{result['rule_name']}: {result['message']}"
        for result in rule_results
        if result.get("status") == "fail"
    ]
    if fail_messages:
        return "Exception Detected", " | ".join(fail_messages)

    warning_messages = [
        f"{result['rule_name']}: {result['message']}"
        for result in rule_results
        if result.get("status") == "warning"
    ]

    semantic_messages: list[str] = []
    if semantic_result:
        if semantic_result.get("needs_human_review"):
            semantic_messages.append(
                normalize_string(semantic_result.get("review_trigger"))
                or "Semantic result is ambiguous and needs manual confirmation."
            )

        category = normalize_string(semantic_result.get("expense_category"))
        confidence = clamp_confidence(semantic_result.get("confidence"))
        if (
            category
            and category not in {"Other", "Unavailable"}
            and confidence >= 0.75
            and not is_semantic_category_compatible(claimed_type, category)
        ):
            semantic_messages.append(
                f"Claimed type '{claimed_type}' differs from semantic category '{category}'."
            )

    review_messages = warning_messages + semantic_messages
    if review_messages:
        return "Needs Human Review", " | ".join(review_messages)

    return (
        "Suggested Pass",
        "Deterministic checks passed and semantic output is sufficiently clear. Final approval remains subject to human review.",
    )

