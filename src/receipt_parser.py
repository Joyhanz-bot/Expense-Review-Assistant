from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .utils import find_expense_id, normalize_string, safe_float


def extract_pdf_text(source: str | Path | Any) -> tuple[str, str | None]:
    try:
        if isinstance(source, (str, Path)):
            reader = PdfReader(str(source))
        else:
            if hasattr(source, "seek"):
                source.seek(0)
            reader = PdfReader(source)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text, None
    except Exception as exc:  # pragma: no cover - defensive path for bad uploads
        return "", f"{exc.__class__.__name__}: {exc}"


def _pick(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_total(text: str) -> tuple[str, float | None]:
    currency = _pick(r"TOTAL:\s*([A-Z]{3})", text)
    amount_text = _pick(r"TOTAL:\s*[A-Z]{3}\s*([\d,]+\.\d{2})", text)
    return currency, safe_float(amount_text)


def _parse_date_details(date_text: str) -> dict[str, Any]:
    date_matches = re.findall(r"\d{4}-\d{2}-\d{2}", date_text)
    parsed_dates = []
    for value in date_matches:
        try:
            parsed_dates.append(datetime.strptime(value, "%Y-%m-%d").date())
        except ValueError:
            continue

    time_matches = re.findall(r"(\d{2}:\d{2})", date_text)
    start_date = parsed_dates[0] if parsed_dates else None
    end_date = parsed_dates[1] if len(parsed_dates) > 1 else start_date

    return {
        "primary_date": start_date,
        "start_date": start_date,
        "end_date": end_date,
        "times": time_matches,
    }


def _parse_nights(description: str, start_date: Any, end_date: Any) -> int | None:
    match = re.search(r"(\d+)\s+nights?", description, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if start_date and end_date and end_date > start_date:
        return (end_date - start_date).days
    return None


def infer_category_hints(text: str) -> list[str]:
    text_lower = normalize_string(text).lower()
    hints: list[str] = []

    hotel_signal = bool(
        re.search(r"merchant:\s*.+hotel", text_lower)
        or re.search(r"\b\d+\s+nights?\b", text_lower)
        or any(keyword in text_lower for keyword in ("lodging", "check-in", "check out"))
    )
    taxi_signal = any(keyword in text_lower for keyword in ("taxi", "cab", "ride", "metrocab"))

    if hotel_signal:
        hints.append("Hotel")

    if (
        "client" in text_lower
        and any(keyword in text_lower for keyword in ("dinner", "lunch", "meal", "food", "guest"))
    ) or "guests" in text_lower:
        hints.append("Client Entertainment")
    elif any(keyword in text_lower for keyword in ("dinner", "lunch", "meal", "food", "bistro", "kitchen")):
        hints.append("Meal")

    if taxi_signal:
        hints.append("Taxi")
    elif any(keyword in text_lower for keyword in ("bus", "train", "rail", "flight", "metro")):
        hints.append("Transportation")

    seen = set()
    ordered_hints = []
    for hint in hints:
        if hint not in seen:
            seen.add(hint)
            ordered_hints.append(hint)
    return ordered_hints


def _parse_line_items(description: str) -> list[dict[str, Any]]:
    parts = [segment.strip() for segment in re.split(r"\s+\+\s+", description) if segment.strip()]
    line_items = []
    for segment in parts:
        amount_match = re.search(r"([A-Z]{3})\s*([\d,]+\.\d{2})", segment)
        line_items.append(
            {
                "text": segment,
                "currency": amount_match.group(1) if amount_match else "",
                "amount": safe_float(amount_match.group(2) if amount_match else None),
                "category_hints": infer_category_hints(segment),
            }
        )
    return line_items


def parse_receipt(source: str | Path | Any, filename: str | None = None) -> dict[str, Any]:
    inferred_filename = filename
    if isinstance(source, Path):
        inferred_filename = source.name
    elif isinstance(source, str):
        inferred_filename = Path(source).name
    elif inferred_filename is None:
        inferred_filename = normalize_string(getattr(source, "name", "uploaded_receipt.pdf"))

    text, parse_error = extract_pdf_text(source)
    merchant = _pick(r"Merchant:\s*(.+)", text)
    city = _pick(r"City:\s*(.+)", text)
    date_text = _pick(r"Date\s*/\s*Time:\s*(.+)", text)
    description = _pick(r"Description:\s*(.+)", text)
    currency, amount = _parse_total(text)
    date_details = _parse_date_details(date_text)
    category_hints = infer_category_hints(f"{merchant} {description} {text}")
    line_items = _parse_line_items(description)

    return {
        "expense_id": find_expense_id(inferred_filename),
        "filename": inferred_filename,
        "merchant": merchant,
        "city": city,
        "date_text": date_text,
        "description": description,
        "currency": currency,
        "amount": amount,
        "primary_date": date_details["primary_date"],
        "start_date": date_details["start_date"],
        "end_date": date_details["end_date"],
        "times": date_details["times"],
        "nights": _parse_nights(description, date_details["start_date"], date_details["end_date"]),
        "category_hints": category_hints,
        "line_items": line_items,
        "raw_text": text,
        "parse_error": parse_error,
    }


def parse_receipts(sources: list[str | Path | Any]) -> list[dict[str, Any]]:
    return [parse_receipt(source) for source in sources]
