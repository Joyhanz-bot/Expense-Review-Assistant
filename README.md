# 💼 费用审核助手 Expense Review Assistant

一个面向 Finance × AI 作品集展示的费用初审 Demo，结合 **Python Rule Engine、Semantic Analysis、Streamlit、Management Reporting Mapping 与 Human Review**，模拟财务人员从报销资料接收到初审结论的完整工作流。

> 本项目默认使用本地规则完成语义分类，不调用外部付费 LLM API。所有报销模板、票据和费用制度均为模拟数据，不包含真实公司内部信息。

## 项目概览

费用审核通常同时包含两类工作：一类可以通过明确制度和结构化字段完成判断，另一类需要理解票据描述、备注或混合费用等非结构化信息。

本项目将两类任务清晰分层：

- **Python Rule Engine** 负责金额、币种、日期、费用标准、住宿晚数、参与人数和加班打车时间等确定性审核。
- **Semantic Analysis** 负责辅助识别费用类别、Mixed Expense 和语义不确定性。公开 Demo 默认采用本地关键词规则，并预留可选 LLM 接口。
- **Human Review** 负责处理规则异常、必要信息缺失、混合费用和低置信度结果，并保留最终审批权。
- **Management Reporting Mapping** 仅为审核通过的记录生成管理报表科目建议，不替代财务人员的最终入账判断。

## 业务背景

人工费用审核经常面临以下问题：

- 报销模板与票据字段需要逐项核对，重复工作较多。
- 金额、币种、日期和费用标准等规则分散，审核口径不易保持一致。
- 票据描述可能不完整，或一张票据同时包含多种费用性质。
- 审核结论与管理报表科目维护相互割裂，需要再次进行人工分类。
- 如果直接让 LLM 判断审批结果，过程难以解释，也不符合财务内控要求。

这个 Demo 的目标不是替代财务审批，而是展示一个更透明、可解释、可人工复核的费用初审流程。

## 解决方案架构

```text
报销 Template + PDF 票据
          |
          v
票据解析与字段匹配
Receipt Parser
          |
          +-----------------------------+
          |                             |
          v                             v
Python Rule Engine              Semantic Analysis
确定性财务规则审核               本地语义规则（默认）
                                        |
          +-----------------------------+
          |
          v
审核结果总览
通过 / 发现异常 / 需人工复核
          |
          +--> 通过记录：生成管理报表科目打标建议
          |
          +--> 异常或不确定记录：进入 Human Review
          |
          v
财务人员最终确认
```

## Python、语义分析与人工复核的职责边界

| 模块 | 负责内容 | 不负责内容 |
| --- | --- | --- |
| **Python Rule Engine** | 金额、币种、日期、字段完整性、费用限额、人数、住宿晚数、加班打车时间等确定性规则 | 不理解复杂票据语义 |
| **Semantic Analysis** | 辅助识别费用类别、Mixed Expense、低置信度和语义歧义 | 不做最终审批，不替代确定性规则 |
| **Human Review** | 复核规则异常、信息缺失和不确定记录，并确认最终处理结果 | 不被系统自动替代 |

这种分工保证了审核结果尽量可解释：能用规则明确判断的内容由 Python 完成，只有传统规则难以稳定处理的语义问题才进入辅助分析。

## 核心功能

- 支持内置模拟数据和自有测试文件上传两种模式。
- 从文本型 PDF 票据中提取商户、日期、时间、币种、金额和描述等字段。
- 将报销 Template 与对应票据进行匹配和字段核验。
- 运行模块化 Python 财务审核规则，并展示具体异常原因。
- 默认通过本地关键词规则进行费用语义分类，无 API Key 也能完整运行。
- 将 Mixed Expense、低置信度或信息不足的记录自动标记为需人工复核。
- 只为审核通过的记录生成管理报表科目打标建议。
- 使用 Streamlit 展示审核总览、规则明细、语义分析和人工复核清单。

## 审核流程 🧭

1. 选择内置模拟数据，或上传报销 Excel Template 与对应 PDF 票据。
2. 解析票据文本，并提取可识别的结构化字段。
3. 根据文件名和费用 ID 将报销记录与票据进行匹配。
4. 运行 Python Rule Engine，检查金额、币种、日期和费用标准等规则。
5. 使用本地语义规则辅助识别费用类别、Mixed Expense 和不确定结果。
6. 输出三类初审状态：`建议通过`、`发现异常`、`需人工复核`。
7. 仅对通过记录生成 Management Reporting Mapping 建议。
8. 将异常及不确定记录交由财务人员复核并最终确认。

> 本工具仅提供费用初审建议，不执行最终审批。最终审批结果仍需由财务人员确认。

## Python Rule Engine

确定性审核逻辑集中在 `src/rule_engine.py`，当前包括：

- 申报金额与票据金额核验
- 币种识别与匹配
- 报销日期与出差期间核验
- 票据日期匹配
- 票据与附件完整性检查
- 住宿晚数与每晚标准检查
- 餐饮费用标准检查
- 客户招待人均标准检查
- 加班打车时间规则检查
- 必要字段缺失检查

每条规则返回标准化结果，包括规则名称、通过状态、说明、标准值和实际值，便于前端展示和人工追溯。

## 语义辅助分析 Semantic Analysis

公开 Demo 当前默认使用**本地关键词规则**进行语义分类，可以识别以下费用类型：

- Taxi / 打车
- Hotel / 住宿
- Meal / 餐饮
- Client Entertainment / 客户招待
- Transportation / 交通
- Mixed Expense / 混合费用
- Other / 其他

项目在 `src/semantic_analyzer.py` 中预留了可选 LLM 接口。只有用户主动配置 `OPENAI_API_KEY` 时，程序才会尝试调用外部模型；未配置 API Key 或调用失败时，系统会继续使用本地规则，不影响 Demo 运行。

无论采用哪种语义分析模式，以下记录都会进入 Human Review：

- Mixed Expense
- 语义分类置信度较低
- 描述信息不足或存在歧义

LLM 不负责输出最终的 Approved / Rejected 结论。

## 管理报表科目打标 📊

`src/reporting_mapper.py` 是独立于审核规则和 Streamlit UI 的管理报表映射层。只有状态为 `建议通过` 的记录才会生成打标建议；`发现异常` 和 `需人工复核` 的记录显示为待确认。

当前 Demo 映射示例：

| 费用类型 | 建议管理报表科目 |
| --- | --- |
| 打车 | 行政费用 > 差旅费 > 出租车/打车费 |
| 加班打车 | 行政费用 > 差旅费 > 加班打车费 |
| 餐饮 | 行政费用 > 差旅费 > 出差餐饮费 |
| 客户招待 | 业务招待费 |
| 短期住宿 | 行政费用 > 差旅费 > 短期出差住宿 |
| 长期住宿 | 行政费用 > 差旅费 > 长期出差住宿 |

住宿分类优先使用票据中的住宿晚数，缺失时使用出差时长作为辅助依据。当前模拟管理口径将 **7 晚及以下**定义为短期住宿，超过 7 晚定义为长期住宿。该阈值仅用于 Demo，可根据企业实际管理制度调整。

## 模拟测试场景

项目内置 1 份模拟报销 Template、1 份模拟费用制度和 8 份模拟 PDF 票据，覆盖：

- 正常打车、住宿、餐饮和客户招待
- 超出费用标准
- 加班打车时间不符合规则
- 参与人数缺失
- Mixed Expense 与低置信度语义判断

所有案例均为合成数据，不对应任何真实员工、供应商或公司报销记录。

## 项目结构

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

## 本地运行 🚀

### 1. 克隆项目

```bash
git clone https://github.com/Joyhanz-bot/expense-review-assistant.git
cd expense-review-assistant
```

### 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 启动 Streamlit

```bash
python3 -m streamlit run app.py
```

启动后可选择：

- **内置模拟数据**：直接运行项目中的 8 条模拟费用案例。
- **上传自有测试文件**：上传 Excel 报销 Template 和对应 PDF 票据。

建议仅使用模拟或脱敏后的文件进行测试。

## 可选 LLM 配置

默认公开 Demo 不需要 API Key，也不会调用外部 LLM API。如需测试预留接口，可通过环境变量配置：

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_MODEL="gpt-4.1-mini"  # 可选
```

- API Key 只从环境变量读取，不会写入源代码。
- 未配置 API Key 时，系统正常使用本地关键词规则。
- 外部模型调用失败时，系统自动回退到本地规则模式。
- 即使启用 LLM，最终审批仍由财务人员完成。

## 数据隐私与公开安全 🔒

- 所有票据均为模拟 PDF。
- 报销 Template 和费用制度均为合成文件。
- 项目不包含真实员工姓名、供应商信息或公司内部政策。
- 项目不包含 API Key、Token、Password 或 `.env` 文件。
- `.gitignore` 已排除本地密钥、缓存、虚拟环境和 Streamlit secrets。

本仓库可用于公开的 GitHub 作品集展示，但使用者仍应避免上传真实敏感报销资料。

## 当前局限

- 票据解析主要面向当前模拟的文本型 PDF，暂不支持扫描图片票据 OCR。
- 费用规则围绕模拟的新加坡差旅场景设计，不代表真实企业制度。
- 本地关键词语义分类适合 Demo，不具备通用票据理解能力。
- 管理报表科目和 7 晚住宿阈值均为模拟管理口径，不等同于企业会计科目表。
- 当前流程面向单个报销包展示，尚未覆盖批量审批、权限管理和审计日志。
- Streamlit 页面以作品集演示和可解释性为目标，不是生产级财务系统。

## 后续可扩展方向

- 增加 OCR 或多模态票据解析，支持扫描件和图片票据。
- 将费用制度抽离为可配置的 YAML / JSON 文件。
- 增加规则引擎、解析器和边界场景的自动化测试。
- 扩展多国家、多币种和多套费用制度的模拟场景。
- 支持导出审核报告和可追溯的审计记录。

---

**Portfolio Positioning:** Finance Workflow Automation × Python × Semantic Analysis × Human-in-the-Loop
