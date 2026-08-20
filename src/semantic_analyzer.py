from __future__ import annotations

import json
import os
import re
from typing import Any

from .receipt_parser import infer_category_hints
from .utils import clamp_confidence, normalize_string

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency fallback
    OpenAI = None


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
LOW_CONFIDENCE_THRESHOLD = 0.70


class SemanticAnalyzer:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = normalize_string(api_key or os.getenv("OPENAI_API_KEY"))
        self.model = normalize_string(model or DEFAULT_MODEL) or "gpt-4.1-mini"
        self.is_llm_enabled = bool(self.api_key and OpenAI is not None)

        if self.is_llm_enabled:
            self.client = OpenAI(api_key=self.api_key)
            self.status_message = "LLM-assisted semantic analysis is enabled."
        else:
            self.client = None
            if self.api_key and OpenAI is None:
                self.status_message = "OpenAI SDK unavailable - running keyword fallback mode."
            else:
                self.status_message = "LLM analysis unavailable - running rule-based demo mode."

    def analyze_receipt(self, receipt: dict[str, Any] | None) -> dict[str, Any]:
        if not receipt:
            return {
                "provider": "unavailable",
                "expense_category": "Unavailable",
                "is_mixed_expense": False,
                "confidence": 0.0,
                "reason": "No matched receipt was available for semantic analysis.",
                "needs_human_review": True,
                "review_trigger": "No receipt matched this claim line.",
                "model": self.model,
                "availability_message": self.status_message,
            }

        if not self.client:
            return self._keyword_fallback(
                receipt,
                availability_message=self.status_message,
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": self._user_prompt(receipt)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            payload = self._parse_json(content)
            return self._normalize_result(
                payload,
                provider="llm",
                availability_message="LLM-assisted semantic analysis",
            )
        except Exception as exc:  # pragma: no cover - network/API path
            return self._keyword_fallback(
                receipt,
                availability_message=f"LLM request failed ({exc.__class__.__name__}) - running keyword fallback mode.",
                error=str(exc),
            )

    def _system_prompt(self) -> str:
        return (
            "You analyze finance receipt text for semantic categorization only. "
            "Do not approve or reject expenses. "
            "Return valid JSON with keys: expense_category, is_mixed_expense, confidence, reason. "
            "Allowed categories: Taxi, Hotel, Meal, Client Entertainment, Transportation, Other, Mixed Expense. "
            "Use Mixed Expense when one receipt clearly contains multiple expense natures. "
            "If the receipt is ambiguous, lower the confidence."
        )

    def _user_prompt(self, receipt: dict[str, Any]) -> str:
        return json.dumps(
            {
                "merchant": receipt.get("merchant"),
                "city": receipt.get("city"),
                "date_text": receipt.get("date_text"),
                "description": receipt.get("description"),
                "line_items": receipt.get("line_items"),
                "raw_text": receipt.get("raw_text"),
            },
            ensure_ascii=False,
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _normalize_result(
        self,
        payload: dict[str, Any],
        provider: str,
        availability_message: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        allowed_categories = {
            "Taxi",
            "Hotel",
            "Meal",
            "Client Entertainment",
            "Transportation",
            "Other",
            "Mixed Expense",
        }
        category = normalize_string(payload.get("expense_category")) or "Other"
        if category not in allowed_categories:
            category = "Other"

        is_mixed_expense = bool(payload.get("is_mixed_expense")) or category == "Mixed Expense"
        confidence = clamp_confidence(payload.get("confidence"))
        reason = normalize_string(payload.get("reason")) or "No semantic explanation returned."

        review_trigger = ""
        if is_mixed_expense:
            review_trigger = "Mixed expense detected."
        elif confidence < LOW_CONFIDENCE_THRESHOLD:
            review_trigger = "Semantic confidence is below the review threshold."

        return {
            "provider": provider,
            "expense_category": category,
            "is_mixed_expense": is_mixed_expense,
            "confidence": confidence,
            "reason": reason,
            "needs_human_review": bool(review_trigger),
            "review_trigger": review_trigger,
            "model": self.model,
            "availability_message": availability_message,
            "error": error,
        }

    def _keyword_fallback(
        self,
        receipt: dict[str, Any],
        availability_message: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        text = " ".join(
            [
                normalize_string(receipt.get("merchant")),
                normalize_string(receipt.get("description")),
                normalize_string(receipt.get("raw_text")),
            ]
        )
        hints = infer_category_hints(text)
        line_item_hints = {
            hint
            for item in receipt.get("line_items", [])
            for hint in item.get("category_hints", [])
        }
        hints = list(dict.fromkeys(hints + list(line_item_hints)))

        if len(hints) > 1:
            payload = {
                "expense_category": "Mixed Expense",
                "is_mixed_expense": True,
                "confidence": 0.55,
                "reason": f"Keyword fallback found multiple category hints: {', '.join(hints)}.",
            }
        elif hints:
            category = hints[0]
            confidence_map = {
                "Hotel": 0.92,
                "Taxi": 0.90,
                "Transportation": 0.82,
                "Meal": 0.84,
                "Client Entertainment": 0.86,
            }
            payload = {
                "expense_category": category,
                "is_mixed_expense": False,
                "confidence": confidence_map.get(category, 0.75),
                "reason": f"Keyword fallback matched receipt text to category '{category}'.",
            }
        else:
            payload = {
                "expense_category": "Other",
                "is_mixed_expense": False,
                "confidence": 0.40,
                "reason": "Keyword fallback could not confidently classify the receipt text.",
            }

        return self._normalize_result(
            payload,
            provider="fallback",
            availability_message=availability_message,
            error=error,
        )

