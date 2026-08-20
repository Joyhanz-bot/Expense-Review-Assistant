from __future__ import annotations

from datetime import time
from typing import Any

from .utils import normalize_string, parse_date_value, safe_float

SYNTHETIC_POLICY = {
    "Singapore": {
        "currency": "SGD",
        "hotel_per_night": 180.0,
        "meal_per_day": 35.0,
        "client_ent_per_person": 100.0,
        "overtime_taxi_cutoff": time(22, 0),
    }
}


def build_rule_result(
    rule_name: str,
    status: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
) -> dict[str, Any]:
    return {
        "rule_name": rule_name,
        "status": status,
        "message": message,
        "expected": expected,
        "actual": actual,
    }


def check_receipt_presence(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any]:
    expected_filename = normalize_string(row.get("附件文件名"))
    if receipt:
        return build_rule_result(
            "receipt_presence",
            "pass",
            "Matched a receipt to this claim line.",
            expected=expected_filename,
            actual=normalize_string(receipt.get("filename")),
        )
    return build_rule_result(
        "receipt_presence",
        "fail",
        "No matching receipt was found for this claim line.",
        expected=expected_filename,
        actual=None,
    )


def check_receipt_parse_error(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not receipt:
        return None
    parse_error = normalize_string(receipt.get("parse_error"))
    if not parse_error:
        return build_rule_result(
            "receipt_text_extraction",
            "pass",
            "Receipt text extraction completed successfully.",
        )
    return build_rule_result(
        "receipt_text_extraction",
        "fail",
        "Receipt text extraction failed.",
        expected="Machine-readable receipt text",
        actual=parse_error,
    )


def check_missing_fields(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any]:
    missing_fields = []
    for field in ("明细ID", "费用日期", "申报费用类型", "币种", "申报金额", "附件文件名"):
        if not normalize_string(row.get(field)) and safe_float(row.get(field)) is None:
            missing_fields.append(f"template:{field}")

    if receipt:
        for field in ("merchant", "date_text", "description", "currency"):
            if not normalize_string(receipt.get(field)):
                missing_fields.append(f"receipt:{field}")
        if safe_float(receipt.get("amount")) is None:
            missing_fields.append("receipt:amount")

    if missing_fields:
        return build_rule_result(
            "missing_field_check",
            "warning",
            "Some required fields are missing and limit deterministic validation.",
            expected="All required fields populated",
            actual=", ".join(missing_fields),
        )

    return build_rule_result(
        "missing_field_check",
        "pass",
        "Required template and receipt fields are available.",
    )


def check_attachment_filename_match(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not receipt:
        return None
    expected_filename = normalize_string(row.get("附件文件名"))
    actual_filename = normalize_string(receipt.get("filename"))
    if not expected_filename:
        return build_rule_result(
            "attachment_filename_match",
            "warning",
            "Template attachment filename is missing.",
            expected="Receipt filename listed in template",
            actual=actual_filename,
        )
    if expected_filename == actual_filename:
        return build_rule_result(
            "attachment_filename_match",
            "pass",
            "Template attachment filename matches the receipt filename.",
            expected=expected_filename,
            actual=actual_filename,
        )
    return build_rule_result(
        "attachment_filename_match",
        "warning",
        "Template attachment filename does not match the matched receipt filename.",
        expected=expected_filename,
        actual=actual_filename,
    )


def check_currency_validation(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not receipt:
        return None
    claimed_currency = normalize_string(row.get("币种"))
    receipt_currency = normalize_string(receipt.get("currency"))
    if not receipt_currency:
        return build_rule_result(
            "currency_validation",
            "warning",
            "Receipt currency could not be extracted.",
            expected=claimed_currency,
            actual=receipt_currency,
        )
    if claimed_currency == receipt_currency:
        return build_rule_result(
            "currency_validation",
            "pass",
            "Claim currency matches the receipt currency.",
            expected=claimed_currency,
            actual=receipt_currency,
        )
    return build_rule_result(
        "currency_validation",
        "fail",
        "Claim currency does not match the receipt currency.",
        expected=claimed_currency,
        actual=receipt_currency,
    )


def check_amount_validation(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not receipt:
        return None
    claimed_amount = safe_float(row.get("申报金额"))
    receipt_amount = safe_float(receipt.get("amount"))
    if receipt_amount is None:
        return build_rule_result(
            "amount_validation",
            "warning",
            "Receipt amount could not be extracted.",
            expected=claimed_amount,
            actual=receipt_amount,
        )
    if claimed_amount is None:
        return build_rule_result(
            "amount_validation",
            "warning",
            "Claimed amount is missing in the template.",
            expected="Numeric amount",
            actual=claimed_amount,
        )
    if abs(claimed_amount - receipt_amount) <= 0.01:
        return build_rule_result(
            "amount_validation",
            "pass",
            "Claimed amount matches the receipt total.",
            expected=claimed_amount,
            actual=receipt_amount,
        )
    return build_rule_result(
        "amount_validation",
        "fail",
        "Claimed amount does not match the receipt total.",
        expected=claimed_amount,
        actual=receipt_amount,
    )


def check_claim_date_in_trip_window(row: dict[str, Any]) -> dict[str, Any]:
    expense_date = parse_date_value(row.get("费用日期"))
    trip_start = parse_date_value(row.get("出差开始"))
    trip_end = parse_date_value(row.get("出差结束"))
    if not expense_date or not trip_start or not trip_end:
        return build_rule_result(
            "claim_date_trip_window",
            "warning",
            "Trip dates or expense date are missing.",
            expected="Expense date within trip window",
            actual=str(expense_date),
        )
    if trip_start <= expense_date <= trip_end:
        return build_rule_result(
            "claim_date_trip_window",
            "pass",
            "Expense date is within the trip window.",
            expected=f"{trip_start} to {trip_end}",
            actual=str(expense_date),
        )
    return build_rule_result(
        "claim_date_trip_window",
        "fail",
        "Expense date is outside the trip window.",
        expected=f"{trip_start} to {trip_end}",
        actual=str(expense_date),
    )


def check_receipt_date_alignment(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not receipt:
        return None
    claim_date = parse_date_value(row.get("费用日期"))
    if not claim_date:
        return build_rule_result(
            "receipt_date_alignment",
            "warning",
            "Claim expense date is missing.",
            expected="Receipt date aligned to claim date",
            actual=normalize_string(receipt.get("date_text")),
        )
    receipt_start = receipt.get("start_date")
    receipt_end = receipt.get("end_date") or receipt_start
    claimed_type = normalize_string(row.get("申报费用类型"))
    if not receipt_start:
        return build_rule_result(
            "receipt_date_alignment",
            "warning",
            "Receipt date could not be extracted.",
            expected=str(claim_date),
            actual=normalize_string(receipt.get("date_text")),
        )
    if claimed_type == "Hotel":
        aligned = receipt_start <= claim_date <= receipt_end
    else:
        aligned = claim_date == receipt_start
    if aligned:
        return build_rule_result(
            "receipt_date_alignment",
            "pass",
            "Receipt date aligns with the claim date.",
            expected=str(claim_date),
            actual=normalize_string(receipt.get("date_text")),
        )
    return build_rule_result(
        "receipt_date_alignment",
        "fail",
        "Receipt date does not align with the claim date.",
        expected=str(claim_date),
        actual=normalize_string(receipt.get("date_text")),
    )


def check_hotel_night_limit(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if normalize_string(row.get("申报费用类型")) != "Hotel":
        return None
    if not receipt:
        return None
    city = normalize_string(row.get("出差城市")) or normalize_string(receipt.get("city"))
    policy = SYNTHETIC_POLICY.get(city, SYNTHETIC_POLICY["Singapore"])
    claimed_amount = safe_float(row.get("申报金额"))
    nights = receipt.get("nights")
    if nights is None:
        return build_rule_result(
            "hotel_night_limit",
            "warning",
            "Hotel nights could not be determined from the receipt.",
            expected=f"<= {policy['hotel_per_night']} per night",
            actual=normalize_string(receipt.get("description")),
        )
    allowed_amount = policy["hotel_per_night"] * nights
    if claimed_amount is not None and claimed_amount <= allowed_amount + 0.01:
        return build_rule_result(
            "hotel_night_limit",
            "pass",
            "Hotel amount is within the synthetic nightly policy limit.",
            expected=allowed_amount,
            actual=claimed_amount,
        )
    return build_rule_result(
        "hotel_night_limit",
        "fail",
        "Hotel amount exceeds the synthetic nightly policy limit.",
        expected=allowed_amount,
        actual=claimed_amount,
    )


def check_meal_daily_limit(row: dict[str, Any], daily_meal_totals: dict[Any, float]) -> dict[str, Any] | None:
    if normalize_string(row.get("申报费用类型")) != "Meal":
        return None
    expense_date = parse_date_value(row.get("费用日期"))
    city = normalize_string(row.get("出差城市")) or "Singapore"
    policy = SYNTHETIC_POLICY.get(city, SYNTHETIC_POLICY["Singapore"])
    if not expense_date:
        return build_rule_result(
            "meal_daily_limit",
            "warning",
            "Meal date is missing, so the daily cumulative rule cannot be checked.",
            expected=f"<= {policy['meal_per_day']} per day",
            actual=None,
        )
    daily_total = daily_meal_totals.get(expense_date, 0.0)
    if daily_total <= policy["meal_per_day"] + 0.01:
        return build_rule_result(
            "meal_daily_limit",
            "pass",
            "Meal claim is within the synthetic daily meal policy limit.",
            expected=policy["meal_per_day"],
            actual=daily_total,
        )
    return build_rule_result(
        "meal_daily_limit",
        "fail",
        "Meal claim exceeds the synthetic daily meal policy limit.",
        expected=policy["meal_per_day"],
        actual=daily_total,
    )


def check_client_ent_per_person_limit(row: dict[str, Any]) -> dict[str, Any] | None:
    if normalize_string(row.get("申报费用类型")) != "Client Entertainment":
        return None
    city = normalize_string(row.get("出差城市")) or "Singapore"
    policy = SYNTHETIC_POLICY.get(city, SYNTHETIC_POLICY["Singapore"])
    participants = safe_float(row.get("参与人数"))
    claimed_amount = safe_float(row.get("申报金额"))
    if participants is None or participants <= 0:
        return build_rule_result(
            "client_ent_per_person_limit",
            "warning",
            "Participant count is missing, so per-person entertainment limit cannot be validated.",
            expected=f"Participant count and <= {policy['client_ent_per_person']} per person",
            actual=row.get("参与人数"),
        )
    per_person_amount = (claimed_amount or 0.0) / participants
    if per_person_amount <= policy["client_ent_per_person"] + 0.01:
        return build_rule_result(
            "client_ent_per_person_limit",
            "pass",
            "Client entertainment cost is within the synthetic per-person policy limit.",
            expected=policy["client_ent_per_person"],
            actual=round(per_person_amount, 2),
        )
    return build_rule_result(
        "client_ent_per_person_limit",
        "fail",
        "Client entertainment cost exceeds the synthetic per-person policy limit.",
        expected=policy["client_ent_per_person"],
        actual=round(per_person_amount, 2),
    )


def check_taxi_overtime_rule(row: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if normalize_string(row.get("申报费用类型")) != "Overtime Taxi":
        return None
    if not receipt:
        return None
    times = receipt.get("times") or []
    city = normalize_string(row.get("出差城市")) or "Singapore"
    policy = SYNTHETIC_POLICY.get(city, SYNTHETIC_POLICY["Singapore"])
    if not times:
        return build_rule_result(
            "taxi_overtime_rule",
            "warning",
            "Receipt time could not be extracted, so overtime taxi timing cannot be validated.",
            expected=f">= {policy['overtime_taxi_cutoff']}",
            actual=normalize_string(receipt.get("date_text")),
        )
    latest_time = max(
        time.fromisoformat(value)
        for value in times
    )
    if latest_time >= policy["overtime_taxi_cutoff"]:
        return build_rule_result(
            "taxi_overtime_rule",
            "pass",
            "Taxi time is within the synthetic overtime taxi rule.",
            expected=str(policy["overtime_taxi_cutoff"]),
            actual=str(latest_time),
        )
    return build_rule_result(
        "taxi_overtime_rule",
        "fail",
        "Taxi time is earlier than the synthetic overtime taxi cutoff.",
        expected=str(policy["overtime_taxi_cutoff"]),
        actual=str(latest_time),
    )


def review_claim_rows(
    claim_df: Any,
    receipts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    receipt_lookup = {receipt.get("expense_id"): receipt for receipt in receipts}

    daily_meal_totals: dict[Any, float] = {}
    for _, row in claim_df.iterrows():
        row_dict = row.to_dict()
        if normalize_string(row_dict.get("申报费用类型")) != "Meal":
            continue
        expense_date = parse_date_value(row_dict.get("费用日期"))
        claimed_amount = safe_float(row_dict.get("申报金额")) or 0.0
        if expense_date:
            daily_meal_totals[expense_date] = daily_meal_totals.get(expense_date, 0.0) + claimed_amount

    audits = []
    for _, row in claim_df.iterrows():
        row_dict = row.to_dict()
        expense_id = normalize_string(row_dict.get("明细ID"))
        receipt = receipt_lookup.get(expense_id)

        rule_results = [
            check_receipt_presence(row_dict, receipt),
            check_receipt_parse_error(receipt),
            check_missing_fields(row_dict, receipt),
            check_attachment_filename_match(row_dict, receipt),
            check_currency_validation(row_dict, receipt),
            check_amount_validation(row_dict, receipt),
            check_claim_date_in_trip_window(row_dict),
            check_receipt_date_alignment(row_dict, receipt),
            check_hotel_night_limit(row_dict, receipt),
            check_meal_daily_limit(row_dict, daily_meal_totals),
            check_client_ent_per_person_limit(row_dict),
            check_taxi_overtime_rule(row_dict, receipt),
        ]

        filtered_rules = [result for result in rule_results if result is not None]
        audits.append(
            {
                "expense_id": expense_id,
                "claimed_type": normalize_string(row_dict.get("申报费用类型")),
                "claimed_amount": safe_float(row_dict.get("申报金额")),
                "currency": normalize_string(row_dict.get("币种")),
                "receipt": receipt,
                "rules": filtered_rules,
            }
        )
    return audits

