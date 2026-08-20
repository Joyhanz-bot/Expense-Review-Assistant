from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.receipt_parser import parse_receipts
from src.reporting_mapper import suggest_reporting_mapping
from src.rule_engine import review_claim_rows
from src.semantic_analyzer import SemanticAnalyzer
from src.utils import (
    SAMPLE_POLICY_PATH,
    SAMPLE_TEMPLATE_PATH,
    clamp_confidence,
    determine_final_status,
    is_semantic_category_compatible,
    list_sample_receipt_paths,
    normalize_string,
    safe_float,
)

st.set_page_config(page_title="费用审核助手", layout="wide")


EXPENSE_TYPE_LABELS = {
    "Taxi": "打车",
    "Overtime Taxi": "加班打车",
    "Hotel": "住宿",
    "Meal": "餐饮",
    "Client Entertainment": "客户招待",
    "Transportation": "交通",
    "Mixed Expense": "混合费用",
    "Other": "其他",
    "Miscellaneous": "杂项",
    "Unavailable": "无法识别",
}

RULE_STATUS_LABELS = {
    "pass": "通过",
    "fail": "异常",
    "warning": "提示",
}

FINAL_STATUS_LABELS = {
    "Suggested Pass": "✅ 通过",
    "Exception Detected": "⚠️ 发现异常",
    "Needs Human Review": "🔴 需人工复核",
}

RULE_DISPLAY_NAMES = {
    "receipt_presence": "票据完整性",
    "receipt_text_extraction": "票据信息读取",
    "missing_field_check": "必要字段检查",
    "attachment_filename_match": "附件匹配",
    "currency_validation": "币种核验",
    "amount_validation": "金额核验",
    "claim_date_trip_window": "报销日期核验",
    "receipt_date_alignment": "票据日期核验",
    "hotel_night_limit": "住宿标准",
    "hotel_limit": "住宿标准",
    "meal_daily_limit": "餐饮标准",
    "meal_limit": "餐饮标准",
    "client_ent_per_person_limit": "客户招待人均标准",
    "taxi_overtime_rule": "加班打车时间规则",
    "overtime_taxi_time": "加班打车时间规则",
}

RULE_REASON_LABELS = {
    "receipt_presence": "缺少对应票据",
    "receipt_text_extraction": "票据信息读取失败",
    "missing_field_check": "缺少必要信息",
    "attachment_filename_match": "票据文件与申报附件不匹配",
    "currency_validation": "申报币种与票据币种不一致",
    "amount_validation": "申报金额与票据金额不一致",
    "claim_date_trip_window": "报销日期不在出差期间",
    "receipt_date_alignment": "票据日期与费用日期不一致",
    "hotel_night_limit": "超出住宿标准",
    "hotel_limit": "超出住宿标准",
    "meal_daily_limit": "超出个人餐饮标准",
    "meal_limit": "超出个人餐饮标准",
    "taxi_overtime_rule": "不满足加班打车时间规则",
    "overtime_taxi_time": "不满足加班打车时间规则",
}

SOURCE_LABELS = {
    "Bundled synthetic sample data": "内置模拟数据",
    "User-uploaded files": "上传自有测试文件",
    "Awaiting uploaded files": "等待上传文件",
}


def display_expense_type(value: Any) -> str:
    normalized = normalize_string(value)
    return EXPENSE_TYPE_LABELS.get(normalized, normalized)


def display_final_status(value: Any) -> str:
    normalized = normalize_string(value)
    return FINAL_STATUS_LABELS.get(normalized, normalized)


def status_icon(value: Any) -> str:
    return display_final_status(value).split(" ", 1)[0]


def status_text(value: Any) -> str:
    label = display_final_status(value)
    return label.split(" ", 1)[1] if " " in label else label


def audit_heading(audit: dict[str, Any]) -> str:
    return (
        f"{status_icon(audit.get('final_status'))} {audit['expense_id']}｜"
        f"{display_expense_type(audit['claimed_type'])}｜{status_text(audit.get('final_status'))}"
    )


def display_source(value: Any) -> str:
    normalized = normalize_string(value)
    return SOURCE_LABELS.get(normalized, normalized)


def display_rule_name(value: Any) -> str:
    normalized = normalize_string(value)
    return RULE_DISPLAY_NAMES.get(normalized, normalized)


def format_claim_amount(currency: Any, amount: Any) -> str:
    currency_text = normalize_string(currency)
    numeric_amount = safe_float(amount)
    if numeric_amount is None:
        amount_text = normalize_string(amount)
    else:
        amount_text = f"{numeric_amount:,.2f}"
    return f"{currency_text} {amount_text}".strip()


def display_rule_value(value: Any) -> str:
    if value is None:
        return "—"
    try:
        if bool(pd.isna(value)):
            return "—"
    except (TypeError, ValueError):
        pass
    return normalize_string(value) or "—"


def display_rule_reason(rule: dict[str, Any]) -> str:
    rule_name = normalize_string(rule.get("rule_name"))
    message = normalize_string(rule.get("message"))
    if rule_name == "client_ent_per_person_limit" and "participant" in message.lower():
        return "缺少参与人数"
    if rule_name in RULE_REASON_LABELS:
        return RULE_REASON_LABELS[rule_name]

    display_name = display_rule_name(rule_name)
    if normalize_string(rule.get("status")) == "fail":
        return f"{display_name}未通过"
    return f"{display_name}需要进一步确认"


def primary_review_reason(audit: dict[str, Any]) -> str:
    attention_rules = [
        rule
        for rule in audit["rules"]
        if normalize_string(rule.get("status")) in {"fail", "warning"}
    ]
    if attention_rules:
        return display_rule_reason(attention_rules[0])

    semantic_result = audit.get("semantic_result") or {}
    if semantic_result.get("is_mixed_expense"):
        return "疑似包含多种费用类型"

    confidence = clamp_confidence(semantic_result.get("confidence"))
    if semantic_result.get("needs_human_review") and confidence < 0.70:
        return "语义判断置信度较低"

    category = normalize_string(semantic_result.get("expense_category"))
    if (
        category
        and category not in {"Other", "Unavailable"}
        and confidence >= 0.75
        and not is_semantic_category_compatible(audit["claimed_type"], category)
    ):
        return "申报类型与识别类型不一致"

    if normalize_string(audit.get("final_status")) == "Suggested Pass":
        return "—"
    return "请展开查看审核明细"


def human_review_focus(audit: dict[str, Any]) -> str:
    focus: list[str] = []
    rules = audit["rules"]
    non_pass_rules = [
        rule for rule in rules if normalize_string(rule.get("status")) != "pass"
    ]
    if any(normalize_string(rule.get("status")) == "fail" for rule in rules):
        focus.append("规则异常")
    if any(
        normalize_string(rule.get("rule_name")) == "missing_field_check"
        and normalize_string(rule.get("status")) != "pass"
        for rule in rules
    ) or any("participant" in normalize_string(rule.get("message")).lower() for rule in non_pass_rules):
        focus.append("缺少必要信息")

    semantic_result = audit.get("semantic_result") or {}
    if semantic_result.get("is_mixed_expense"):
        focus.append("混合费用")
    if semantic_result.get("needs_human_review") and clamp_confidence(
        semantic_result.get("confidence")
    ) < 0.70:
        focus.append("语义置信度较低")

    return "、".join(dict.fromkeys(focus)) or "需要进一步确认"


def claim_row_for_audit(claim_df: pd.DataFrame, audit: dict[str, Any]) -> dict[str, Any]:
    if claim_df.empty or "明细ID" not in claim_df.columns:
        return {}
    matches = claim_df[claim_df["明细ID"].astype(str) == str(audit["expense_id"])]
    return matches.iloc[0].to_dict() if not matches.empty else {}


def build_reporting_mappings(
    audits: list[dict[str, Any]],
    claim_df: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    mappings: dict[str, dict[str, str]] = {}
    for audit in audits:
        mapping = suggest_reporting_mapping(audit, claim_row_for_audit(claim_df, audit))
        if mapping:
            mappings[audit["expense_id"]] = mapping
    return mappings


def display_claim_value(claim_row: dict[str, Any], field: str, fallback: str = "缺失") -> str:
    value = normalize_string(claim_row.get(field))
    return value or fallback


def attention_reasons(audit: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    non_pass_rules = [
        rule
        for rule in audit["rules"]
        if normalize_string(rule.get("status")) in {"fail", "warning"}
    ]
    for rule in non_pass_rules:
        rule_name = normalize_string(rule.get("rule_name"))
        message = normalize_string(rule.get("message"))
        if rule_name == "client_ent_per_person_limit" and "participant" in message.lower():
            reasons.append("缺少参与人数，无法完成客户招待人均标准判断。")
        else:
            reasons.append(f"{display_rule_reason(rule)}。")

    semantic_result = audit.get("semantic_result") or {}
    confidence = clamp_confidence(semantic_result.get("confidence"))
    if semantic_result.get("is_mixed_expense"):
        mixed_reason = "疑似包含多种费用类型"
        if confidence < 0.70:
            mixed_reason += "，且语义分类置信度较低"
        reasons.append(f"{mixed_reason}。")
    elif semantic_result.get("needs_human_review") and confidence < 0.70:
        reasons.append("语义分类置信度较低，需要人工判断。")

    if not reasons:
        reasons.append(primary_review_reason(audit))
    return list(dict.fromkeys(reasons))


def recommended_action(audit: dict[str, Any]) -> str:
    non_pass_rules = [
        rule
        for rule in audit["rules"]
        if normalize_string(rule.get("status")) in {"fail", "warning"}
    ]
    rule_names = {normalize_string(rule.get("rule_name")) for rule in non_pass_rules}
    if "client_ent_per_person_limit" in rule_names and any(
        "participant" in normalize_string(rule.get("message")).lower()
        for rule in non_pass_rules
    ):
        return "补充参与人数后重新审核。"
    if "taxi_overtime_rule" in rule_names:
        return "核对加班时段及票据时间，确认符合制度后重新审核。"
    if "meal_daily_limit" in rule_names:
        return "根据费用制度核对餐饮标准，调整申报或补充说明后重新审核。"
    if "hotel_night_limit" in rule_names:
        return "根据费用制度核对住宿标准，确认后重新审核。"
    if any("missing" in name for name in rule_names):
        return "补充缺失信息后重新审核。"

    semantic_result = audit.get("semantic_result") or {}
    confidence = clamp_confidence(semantic_result.get("confidence"))
    if semantic_result.get("is_mixed_expense"):
        return "人工确认费用性质，并判断是否需要拆分报销。"
    if semantic_result.get("needs_human_review") and confidence < 0.70:
        return "补充费用说明并由财务人员确认费用类别。"
    return "由财务人员进一步确认后处理。"


def render_attention_card(audit: dict[str, Any], claim_df: pd.DataFrame) -> None:
    claim_row = claim_row_for_audit(claim_df, audit)
    receipt = audit.get("receipt") or {}
    final_status = normalize_string(audit.get("final_status"))
    expense_type = display_expense_type(audit["claimed_type"])

    with st.container(border=True):
        if final_status == "Exception Detected":
            st.warning(f"**{audit_heading(audit)}**")
        else:
            st.error(f"**{audit_heading(audit)}**")

        st.markdown("**原始申报信息**")
        claim_col1, claim_col2, claim_col3 = st.columns(3)
        claim_col1.write(f"费用ID：{audit['expense_id']}")
        claim_col2.write(f"费用类型：{expense_type}")
        claim_col3.write(f"日期：{display_claim_value(claim_row, '费用日期')}")
        claim_col1.write(
            f"申报金额：{format_claim_amount(audit['currency'], audit['claimed_amount'])}"
        )
        claim_col2.write(f"币种：{display_claim_value(claim_row, '币种', audit['currency'])}")
        claim_col3.write(f"参与人数：{display_claim_value(claim_row, '参与人数')}")
        st.markdown(f"业务描述：{display_claim_value(claim_row, '业务描述')}")

        st.markdown("**对应票据信息**")
        receipt_col1, receipt_col2, receipt_col3 = st.columns(3)
        receipt_col1.write(
            f"票据文件：{normalize_string(receipt.get('filename')) or display_claim_value(claim_row, '附件文件名')}"
        )
        receipt_col2.write(f"商户：{normalize_string(receipt.get('merchant')) or '未读取'}")
        receipt_col3.write(f"票据日期：{normalize_string(receipt.get('date_text')) or '未读取'}")
        receipt_col1.write(
            "票据金额："
            + (
                format_claim_amount(receipt.get("currency"), receipt.get("amount"))
                if safe_float(receipt.get("amount")) is not None
                else "未读取"
            )
        )
        receipt_col2.write(f"票据描述：{normalize_string(receipt.get('description')) or '未读取'}")

        semantic_result = audit.get("semantic_result") or {}
        if final_status == "Needs Human Review":
            st.markdown(
                f"识别类型：{display_expense_type(semantic_result.get('expense_category'))}　"
                f"置信度：{clamp_confidence(semantic_result.get('confidence')):.2f}"
            )

        st.markdown("**核心原因**")
        for reason in attention_reasons(audit):
            st.markdown(f"- {reason}")
        if final_status == "Needs Human Review":
            st.markdown("建议打标：待复核后确认")
        else:
            st.markdown("建议打标：—")
        st.markdown(f"**建议处理：**{recommended_action(audit)}")


def render_exception_and_human_review(audits: list[dict[str, Any]], claim_df: pd.DataFrame) -> None:
    st.subheader("6. 异常与人工复核 Exception & Human Review")
    rule_exceptions = [
        audit for audit in audits if normalize_string(audit.get("final_status")) == "Exception Detected"
    ]
    human_reviews = [
        audit for audit in audits if normalize_string(audit.get("final_status")) == "Needs Human Review"
    ]

    st.markdown("### ⚠️ 规则异常")
    if rule_exceptions:
        for audit in rule_exceptions:
            render_attention_card(audit, claim_df)
    else:
        st.caption("暂无 Python 确定性规则识别出的明确异常。")

    st.markdown("### 🔴 需人工判断")
    if human_reviews:
        for audit in human_reviews:
            render_attention_card(audit, claim_df)
    else:
        st.caption("暂无需要人工判断的记录。")

    st.caption("本工具仅提供费用初审建议，不执行最终审批。最终审批结果仍需由财务人员确认。")


def load_claim_dataframe(source: Any) -> pd.DataFrame:
    return pd.read_excel(source, sheet_name="Expense Claim")


def get_data_source(
    mode: str,
    uploaded_template: Any,
    uploaded_receipts: list[Any],
) -> tuple[pd.DataFrame | None, list[Any], str]:
    if mode == "Bundled sample data":
        return (
            load_claim_dataframe(SAMPLE_TEMPLATE_PATH),
            list_sample_receipt_paths(),
            "Bundled synthetic sample data",
        )

    if uploaded_template is None:
        return None, [], "Awaiting uploaded files"

    return (
        load_claim_dataframe(uploaded_template),
        uploaded_receipts,
        "User-uploaded files",
    )


def render_header() -> None:
    st.title("费用审核助手")
    st.caption("Expense Review Assistant · Python Rule Engine + Semantic Analysis + Human Review")
    st.info(
        "用于模拟财务费用初审流程。Python 负责确定性规则审核，语义分析用于辅助识别复杂费用类型，"
        "异常及不确定情况保留人工复核。所有数据均为模拟数据。"
    )


def render_sidebar() -> tuple[str, Any, list[Any]]:
    st.sidebar.header("Demo 控制台")
    source_options = ["Bundled sample data", "Upload your own files"]
    source_display_labels = {
        "Bundled sample data": "内置模拟数据",
        "Upload your own files": "上传自有测试文件",
    }
    mode = st.sidebar.radio(
        "选择数据来源",
        source_options,
        format_func=lambda value: source_display_labels[value],
        help="内置选项使用项目中的模拟报销模板和 8 份模拟 PDF 票据。",
    )

    uploaded_template = None
    uploaded_receipts: list[Any] = []
    if mode == "Upload your own files":
        uploaded_template = st.sidebar.file_uploader("报销模板（.xlsx）", type=["xlsx"])
        uploaded_receipts = st.sidebar.file_uploader(
            "票据文件（PDF）",
            type=["pdf"],
            accept_multiple_files=True,
        )
    else:
        st.sidebar.markdown("**模拟文件**")
        st.sidebar.caption(f"模拟报销模板: `{SAMPLE_TEMPLATE_PATH.name}`")
        st.sidebar.caption(f"模拟票据: `{len(list_sample_receipt_paths())}` 份 PDF")
        st.sidebar.caption(f"模拟费用制度: `{SAMPLE_POLICY_PATH.name}`")

    return mode, uploaded_template, uploaded_receipts


def render_claim_overview(claim_df: pd.DataFrame, receipt_sources: list[Any], source_label: str) -> None:
    st.subheader("1. 报销概览")

    overview_df = claim_df[
        ["明细ID", "费用日期", "业务描述", "申报费用类型", "币种", "申报金额", "参与人数", "附件文件名"]
    ].copy()
    overview_df["申报费用类型"] = overview_df["申报费用类型"].map(display_expense_type)
    overview_df = overview_df.rename(
        columns={
            "明细ID": "费用ID",
            "费用日期": "日期",
            "业务描述": "业务描述",
            "申报费用类型": "费用类型",
            "币种": "币种",
            "申报金额": "金额",
            "参与人数": "参与人数",
            "附件文件名": "票据文件",
        }
    )
    st.dataframe(
        overview_df,
        width="stretch",
        hide_index=True,
    )
    st.caption(f"数据来源：{display_source(source_label)}")


def render_review_kpis(claim_df: pd.DataFrame, audits: list[dict[str, Any]]) -> None:
    currencies = ", ".join(sorted(claim_df["币种"].astype(str).unique()))
    total_claimed = claim_df["申报金额"].fillna(0).sum()
    status_counts = pd.Series([audit["final_status"] for audit in audits]).value_counts()
    suggested_pass = int(status_counts.get("Suggested Pass", 0))
    exceptions = int(status_counts.get("Exception Detected", 0))
    human_review = int(status_counts.get("Needs Human Review", 0))

    st.markdown("### 审核概况")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("申报总额", f"{currencies} {total_claimed:,.2f}")
    col2.metric("费用笔数", len(claim_df))
    col3.metric("✅ 通过笔数", suggested_pass)
    col4.metric("⚠️/🔴 需关注笔数", exceptions + human_review)


def build_semantic_placeholder() -> dict[str, Any]:
    return {
        "provider": "unavailable",
        "expense_category": "Unavailable",
        "is_mixed_expense": False,
        "confidence": 0.0,
        "reason": "No semantic analysis was run for this line.",
        "needs_human_review": False,
        "review_trigger": "",
        "availability_message": "",
    }


def run_review(claim_df: pd.DataFrame, receipt_sources: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], SemanticAnalyzer]:
    receipts = parse_receipts(receipt_sources)
    analyzer = SemanticAnalyzer()
    semantic_results = {
        receipt["expense_id"]: analyzer.analyze_receipt(receipt)
        for receipt in receipts
    }
    audits = review_claim_rows(claim_df, receipts)
    for audit in audits:
        semantic_result = semantic_results.get(audit["expense_id"], build_semantic_placeholder())
        final_status, final_reason = determine_final_status(
            audit["rules"],
            audit["claimed_type"],
            semantic_result,
        )
        audit["semantic_result"] = semantic_result
        audit["final_status"] = final_status
        audit["final_reason"] = final_reason
    return receipts, audits, analyzer


def render_receipt_table(receipts: list[dict[str, Any]]) -> None:
    with st.expander("票据解析详情", expanded=False):
        receipt_df = pd.DataFrame(receipts)
        if receipt_df.empty:
            st.write("暂无可用票据数据。")
            return
        receipt_display_df = receipt_df[
            [
                "expense_id",
                "filename",
                "merchant",
                "city",
                "date_text",
                "description",
                "currency",
                "amount",
                "nights",
            ]
        ].rename(
            columns={
                "expense_id": "费用ID",
                "filename": "文件名",
                "merchant": "商户",
                "city": "城市",
                "date_text": "票据日期",
                "description": "费用描述",
                "currency": "币种",
                "amount": "金额",
                "nights": "住宿晚数",
            }
        )
        st.dataframe(
            receipt_display_df,
            width="stretch",
            hide_index=True,
        )


def render_review_summary(
    audits: list[dict[str, Any]],
    reporting_mappings: dict[str, dict[str, str]],
) -> None:
    st.subheader("2. 审核结果")
    summary_rows = [
        {
            "费用ID": audit["expense_id"],
            "费用类型": display_expense_type(audit["claimed_type"]),
            "金额": format_claim_amount(audit["currency"], audit["claimed_amount"]),
            "审核结果": display_final_status(audit["final_status"]),
            "主要原因": primary_review_reason(audit),
            "建议打标科目": reporting_mappings.get(audit["expense_id"], {}).get(
                "mapping_path", "—"
            ),
        }
        for audit in audits
    ]
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)


def render_reporting_mapping(
    audits: list[dict[str, Any]],
    reporting_mappings: dict[str, dict[str, str]],
) -> None:
    st.subheader("3. 通过项打标建议")
    approved_audits = [
        audit for audit in audits if normalize_string(audit.get("final_status")) == "Suggested Pass"
    ]
    mapping_rows = [
        {
            "费用ID": audit["expense_id"],
            "原费用类型": display_expense_type(audit["claimed_type"]),
            "建议打标科目": reporting_mappings[audit["expense_id"]]["mapping_path"],
            "映射依据": reporting_mappings[audit["expense_id"]]["mapping_reason"],
        }
        for audit in approved_audits
        if audit["expense_id"] in reporting_mappings
    ]
    if mapping_rows:
        st.dataframe(pd.DataFrame(mapping_rows), width="stretch", hide_index=True)
    else:
        st.info("当前没有可生成管理报表打标建议的通过记录。")
    st.caption("以上为系统建议打标结果，可由财务人员在最终入账/管理报表维护前人工确认。")


def render_rule_checks(audits: list[dict[str, Any]]) -> None:
    st.subheader("4. 规则审核明细 Rule-based Checks")
    st.caption("默认只展示每笔费用的审核结论；展开后可查看 Python Rule Engine 的逐项核验。")
    for audit in audits:
        with st.expander(
            audit_heading(audit),
            expanded=False,
        ):
            detail_df = pd.DataFrame(
                [
                    {
                        "审核规则": display_rule_name(rule["rule_name"]),
                        "结果": RULE_STATUS_LABELS.get(rule["status"], rule["status"]),
                        "说明": display_rule_value(rule["message"]),
                        "标准值": display_rule_value(rule["expected"]),
                        "实际值": display_rule_value(rule["actual"]),
                    }
                    for rule in audit["rules"]
                ]
            )
            st.dataframe(detail_df, width="stretch", hide_index=True)


def render_semantic_analysis(audits: list[dict[str, Any]], analyzer: SemanticAnalyzer) -> None:
    st.subheader("5. 语义辅助分析 Semantic Analysis")
    if analyzer.is_llm_enabled:
        st.info("当前使用 LLM 进行语义辅助分析。Python 规则仍负责确定性审核，最终结果不由 LLM 单独决定。")
    else:
        st.info("当前 Demo 默认使用本地规则进行语义分类，并已预留 LLM 接口，可按需接入外部模型。")

    semantic_rows = []
    for audit in audits:
        semantic_result = audit["semantic_result"]
        semantic_rows.append(
            {
                "费用ID": audit["expense_id"],
                "申报类型": display_expense_type(audit["claimed_type"]),
                "识别类型": display_expense_type(semantic_result.get("expense_category")),
                "是否混合费用": "是" if semantic_result.get("is_mixed_expense") else "否",
                "置信度": f"{semantic_result.get('confidence', 0.0):.2f}",
            }
        )
    st.dataframe(pd.DataFrame(semantic_rows), width="stretch", hide_index=True)

def main() -> None:
    render_header()
    mode, uploaded_template, uploaded_receipts = render_sidebar()

    try:
        claim_df, receipt_sources, source_label = get_data_source(
            mode,
            uploaded_template,
            uploaded_receipts,
        )
    except Exception as exc:
        st.error(f"读取报销数据失败：{exc}")
        return

    if claim_df is None:
        st.write("请上传 Excel 报销模板和对应 PDF 票据，或切换到内置模拟数据。")
        return

    ready_to_run = bool(receipt_sources)
    if not ready_to_run:
        st.info("请至少添加一份票据 PDF 后再运行审核。")
        return

    if st.button("运行费用审核", type="primary", width="stretch"):
        with st.spinner("正在运行确定性规则审核与语义分析..."):
            receipts, audits, analyzer = run_review(claim_df, receipt_sources)
        reporting_mappings = build_reporting_mappings(audits, claim_df)

        render_review_kpis(claim_df, audits)
        render_claim_overview(claim_df, receipt_sources, source_label)
        render_review_summary(audits, reporting_mappings)
        render_reporting_mapping(audits, reporting_mappings)
        render_rule_checks(audits)
        render_semantic_analysis(audits, analyzer)
        render_receipt_table(receipts)
        render_exception_and_human_review(audits, claim_df)


if __name__ == "__main__":
    main()
