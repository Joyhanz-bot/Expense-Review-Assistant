# Expense Review Assistant

A Finance x AI portfolio project that demonstrates a first-pass expense review workflow using Python deterministic rules, local semantic analysis, Streamlit, management reporting suggestions, and human review. The public demo runs without an external LLM API by default.

## 1. Project Overview

This repository simulates how finance teams can review a single travel claim with multiple receipts before final approval.

It is intentionally scoped as a portfolio demo:

- Python handles deterministic financial checks
- The optional LLM interface is limited to semantic interpretation of unstructured receipt text
- Human review remains in the loop for ambiguous or exceptional cases

All demo files are synthetic. No confidential company policy, real employee data, or real reimbursement documents are included.

## 2. Business Problem

Expense review often mixes two very different tasks:

- Deterministic checks that can be validated with hard rules
- Semantic interpretation that depends on noisy receipt text and descriptions

If these responsibilities are blurred, the result is hard to explain, hard to audit, and risky for finance operations.

This demo shows a cleaner split:

- Python validates amounts, dates, currencies, policy limits, participant counts, hotel nights, and overtime taxi timing
- The optional LLM interface only helps interpret receipt semantics such as category ambiguity or mixed-expense signals
- Final approval is never delegated to the model

## 3. Solution Architecture

```text
Expense claim template + PDF receipts
        |
        v
Receipt Parser (PDF text extraction + structured fields)
        |
        +--> Python Rule Engine (deterministic finance checks)
        |
        +--> Semantic Analyzer (local keyword mode by default; optional LLM interface)
        |
        +--> Management Reporting Mapper (approved lines only)
        |
        v
Streamlit Review Dashboard
        |
        v
Suggested Pass / Exception Detected / Needs Human Review
```

## 4. Python vs LLM Responsibility

### Python deterministic rule engine

Python owns all checks that can be evaluated reliably from structured data:

- amount validation
- currency validation
- template vs receipt field checks
- trip date window checks
- hotel nightly limit checks
- meal daily limit checks
- client entertainment per-person limit checks
- overtime taxi time checks
- missing field checks

### Semantic analysis and optional LLM interface

The public demo currently uses local keyword-based semantic classification. An LLM interface is reserved for optional use when a user explicitly supplies an API key; the checked-in public demo does not call an external LLM API.

If enabled outside the default public path, the LLM is limited to semantic interpretation tasks that are hard to solve with deterministic rules alone:

- infer likely expense category from receipt text
- detect mixed-expense receipts
- surface ambiguous descriptions with low confidence

The LLM does not approve or reject claims.

## 5. Key Features

- Streamlit UI with bundled sample mode and upload mode
- PDF receipt parsing without relying on the LLM
- Modular `src/` structure for parser, rule engine, semantic layer, and utilities
- Optional OpenAI SDK integration through `OPENAI_API_KEY`; not used by the default public demo
- Safe local fallback mode when no API key is configured
- Human-review-oriented output with transparent reasons

## 6. Workflow

1. Load the bundled synthetic claim package or upload your own `.xlsx` + PDF files.
2. Parse receipt text into structured fields such as merchant, date/time, currency, amount, and description.
3. Run deterministic finance checks in Python.
4. Run local keyword-based semantic classification in the default public demo mode.
5. Keep an optional LLM interface available for explicit, user-provided configuration; the published demo does not call an external LLM API.
6. Output one of three review states:
   - `Suggested Pass`
   - `Exception Detected`
   - `Needs Human Review`
7. Generate management reporting subject suggestions only for `Suggested Pass` records.
8. Keep exceptions and uncertain records in the Human Review queue.

Final approval remains subject to human review.

## 7. Management Reporting Mapping

After deterministic review, only records with `Suggested Pass` receive a management reporting subject suggestion. `Exception Detected` and `Needs Human Review` records do not receive an automatic final subject.

The mapping layer is implemented in `src/reporting_mapper.py` and is separate from both the rule engine and the Streamlit UI. It currently provides synthetic demo mappings for taxi, overtime taxi, meal, client entertainment, and hotel expenses.

For hotel expenses, the mapper uses receipt nights first and trip duration as a fallback. The current simulated management convention treats stays of 7 nights or fewer as `短期出差住宿` and stays longer than 7 nights as `长期出差住宿`. This threshold is a demo configuration and should be adjusted to match an organisation's actual management reporting policy before operational use.

The output is a suggestion for finance review, not a posting instruction. Finance staff should confirm the subject before final accounting or management reporting maintenance.

## 8. Demo / Screenshots

- Bundled sample data includes 8 synthetic receipt PDFs covering Taxi, Hotel, Meal, Client Entertainment, Overtime Taxi, and Mixed Expense scenarios.
- The `screenshots/` folder is prepared for Streamlit UI captures before publishing the repo on GitHub.

## 9. Project Structure

```text
expense-review-assistant/
├── README.md
├── app.py
├── requirements.txt
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── receipt_parser.py
│   ├── reporting_mapper.py
│   ├── rule_engine.py
│   ├── semantic_analyzer.py
│   └── utils.py
├── sample_data/
│   ├── expense_template.xlsx
│   ├── Mock_Travel_Expense_Policy.pdf
│   └── receipts/
└── screenshots/
```

## 10. How to Run

```bash
pip install -r requirements.txt
python3 -m streamlit run app.py
```

When the app opens, choose one of these paths:

- `Bundled sample data`: runs the included synthetic demo immediately
- `Upload your own files`: upload an Excel claim template and matching PDF receipts

## 11. LLM Configuration

The default public demo does not require an API key and does not call an external LLM API. The optional interface reads a key from the environment and never hardcodes secrets in source files.

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Optional:

```bash
export OPENAI_MODEL="gpt-4.1-mini"
```

Default public behavior:

- Without `OPENAI_API_KEY`, the app uses local keyword-based semantic classification.
- The checked-in synthetic demo contains no API key and does not call an external LLM API.

Optional behavior:

- If `OPENAI_API_KEY` is present, the app will attempt LLM-assisted semantic analysis.
- If `OPENAI_API_KEY` is missing, the app still runs normally in fallback demo mode.
- If the API call fails, the app falls back to keyword-based semantic classification instead of crashing.

## 12. Demo Data & Privacy

- All receipts are synthetic sample PDFs
- The expense template is synthetic
- The travel policy PDF is a synthetic mock policy
- No real employees, vendors, passwords, or internal company records are included

This repo is designed to be safe for public GitHub sharing as a portfolio project.

## 13. Limitations

- The bundled receipt parser currently targets text-based synthetic PDFs, not scanned image receipts
- Policy logic is intentionally simplified and centered on the bundled Singapore demo scenario
- Semantic analysis is single-receipt classification, not a full enterprise approval workflow
- Management reporting mappings use synthetic demo categories and a configurable 7-night hotel threshold; they are not a substitute for an organisation's chart of accounts or accounting policy
- No OCR pipeline is included yet for image-heavy receipts
- The UI is optimized for demo clarity rather than production-scale operations

## 14. Future Improvements

- Add OCR or multimodal receipt ingestion for non-text PDFs and images
- Expand policy configuration into editable external YAML or JSON files
- Add test coverage for rule outputs and parser edge cases
- Support multi-country demo policies beyond the current bundled scenario
- Export review results as a downloadable audit report
