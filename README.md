# ETL Agent — 医疗脏数据智能清洗流水线

AI 驱动的 ETL 清洗流水线，用 **规则 + Schema 校验 + AI 推理 + LLM Agent** 四阶段处理医疗脏数据。支持自定义 Schema，自动生成清洗规则与推理规则，输出质量报告。

---

## 项目结构

```
AI_schema_ETL/
├── run.py                         # 入口：串联 4 个步骤
├── config.py                      # API 配置（Key、URL、模型名）
├── data/
│   ├── standard_schema.json       # Schema 定义（字段类型、标准值、范围、描述）
│   ├── super_dirty_data.csv       # [生成] Step 1 造的脏数据
│   └── auto_rules.json            # [生成] Step 2 AI 生成的规则
├── output/
│   ├── final_cleaned.csv          # [生成] Step 3 清洗结果
│   └── quality_report.json        # [生成] Step 4 质量报告
└── src/
    ├── logger.py                  # 控制台格式化输出工具（GBK 安全）
    ├── rule_generator.py           # Step 2: AI 扫描数据 → 生成规则
    ├── rule_cleaner.py            # Step 3 P1: 规则查表清洗（毫秒级）
    ├── llm_cleaner.py             # Step 3 P3: LLM 语义清洗（秒级，可并发）
    ├── etl_pipeline.py            # Step 3: 编排器（规则 → AI推理 → Schema校验 → Agent）
    ├── quality_reporter.py        # Step 4: 统计完整度和合规率
    └── __init__.py
```

---

## 核心理念

### AI 做一次理解，代码做 N 次执行

```
AI (1 次 API 调用)
  │
  ├── 理解数据分布 → 生成字段映射规则（raw→clean）
  ├── 理解 Schema 约束 → 确保规则符合标准值
  ├── 凭医学知识生成跨字段推理规则（科室→性别）
  └── 清洗剩余模糊值
          │
代码 (纯本地，N 次)
  │
  ├── 查表替换（毫秒级 × 所有行）
  ├── 应用推理规则填补空值（零 Token）
  ├── Schema 合规校验
  └── 质量统计
```

### Schema 驱动，零硬编码

所有 Prompt 中**不包含任何字段级指引**。字段的清洗目标完全由 `standard_schema.json` 定义：

```json
{
  "name": "drug_name",
  "type": "string",
  "description": "药品通用名（去除剂型后缀）"
}
```

AI 读取 Schema 的 `description`、`type`、`standard_values`、`min/max`，利用自身医学知识判断如何清洗。改数据只需改 Schema JSON，Prompt 不用动。

---

## 执行流程

```
                     +-----------+
                     |  脏数据    |
                     +-----+-----+
                           |
              Step 1 — 生成脏数据（纯本地）
                           |
              Step 2 — 1 次调 LLM
                           |
              +------------v-----------+
              |  RuleGenerator      |
              |  扫描唯一值 → 发给 LLM  |
              |  LLM 一次性输出:        |
              |  · 字段映射规则          |
              |  · 跨字段推理规则        |
              +------------+-----------+
                           |
              auto_rules.json
              ├── gender: {"M":"男", "先生":"男", ...}
              ├── age:    {"35岁":35, "三十":30, "6个月":0, ...}
              ├── drug_name: {"AMX":"阿莫西林", "布洛芬胶囊":"布洛芬", ...}
              └── inference: {"dept_name":{"妇科":{"gender":"女"}, ...}}
                           |
              Step 3 — ETL 清洗（纯本地执行）
                           |
     P1  规则查表        毫秒级逐行替换
                           |
     P2  AI 推理         直接执行 inference 规则
                           |
     P3  Schema 校验      非标值/空值标记
                           |
     P4  Agent 清洗       仅处理剩余脏行（并发）
                           |
              Step 4 — 质量报告（纯本地统计）
```

### Step 1 — 制造脏数据

生成 200 行模拟医疗 CSV，每行包含 6 个字段，覆盖大量脏数据类型。

| 字段 | 脏值种类 | 覆盖类型 |
|------|---------|---------|
| `gender` | ~90 | 英文变体(M/F/Male)、数字(1/2)、尊称(先生/女士)、拼音(nan/nv)、错别字(难/蓝)、嵌入文本("性别：男") |
| `age` | ~70 | 中文数字(三十岁)、带单位(35岁)、约数(约30岁)、婴幼儿(5个月)、极端值(300/999) |
| `dept_name` | ~60 | 全称/简称、楼层编号、英文(Neurology/ER)、ICU变体、括号后缀 |
| `drug_name` | ~50 | 带剂型(分散片)、带规格(0.25g)、品牌名(芬必得)、缩写(AMXL/APAP) |
| `diagnosis_code` | ~70 | 标准ICD-10、中文诊断名、缩写(htn/DM)、格式错误(I-10、E11。9) |

前 10 行为预定义的**跨字段缺失场景**（如 gender 为空 + 妇科），用于验证推理能力。

### Step 2 — AI 生成规则（1 次 API 调用）

扫描脏数据每列的唯一值，连同 Schema 约束一起发给 LLM，一次性输出两类规则：

```
auto_rules.json 结构:
├── gender:     {"M":"男", "male":"男", "F":"女", "帅哥":"男", ...}
├── age:        {"35岁":35, "三十":30, "6个月":0, ...}
├── dept_name:  {"妇产科":"妇科", "ICU":"急诊科", "心内二科":"内科", ...}
├── drug_name:  {"AMX":"阿莫西林", "布洛芬胶囊":"布洛芬", ...}
├── diagnosis:  {"i10":"I10", "高血压":"I10", "E11。9":"E11.9", ...}
└── inference:  {                          ← AI 凭医学知识生成
    "dept_name": {
      "妇科":  {"gender": "女"},
      "产科":  {"gender": "女"},
      "泌尿外科": {"gender": "男"}
    }
  }
```

**inference** 段是 AI 根据自身医学知识直接生成的跨字段推理规则，不需要代码从数据中反向发现，也不受噪音数据干扰。

### Step 3 — ETL 清洗（四阶段，全本地执行）

#### Phase 1 — 规则清洗（毫秒级）

`RuleCleaner` 逐行查 `field_maps` 替换。key 做 `.strip().lower()` 归一化匹配。`patient_id` 透传，age 始终通过 `_clean_age` 校验确保整数输出。

#### Phase 2 — AI 推理（零 Token，零 API）

直接加载 `auto_rules.json` 的 `inference` 段，对 source 字段匹配且 target 为 null 的行应用推理值。不需要任何统计、分组、计算。

```
推理: dept_name='妇科' -> gender='女'
推理: dept_name='产科' -> gender='女'
推理: dept_name='泌尿外科' -> gender='男'
```

#### Phase 3 — Schema 合规校验

对规则+推理结果的每个字段做 3 项检查：

| 检查 | 触发条件 | 示例 |
|------|---------|------|
| 类型检查 | `type=integer` 且值非整数 | `age=0.5` → 不合规 |
| 标准值检查 | `standard_values` 已定义 | `dept_name="妇产科"` → 不合规 |
| 范围检查 | `min`/`max` 已定义 | `age=200` → 不合规 |

不符合的字段标记为"需要 Agent 处理"。同时检查 string 字段的值是否为字符串类型，防止数字等类型混入。

#### Phase 4 — Agent 语义清洗（秒级，可并发）

对仍有问题的行，并发调 LLM（`ThreadPoolExecutor`，默认 10 并发）。合并策略：

```
规则值 = null     → 用 Agent 结果填补
规则值不合规      → 用 Agent 结果替换（如 "妇产科" → "妇科"）
规则值已合规      → 保留，不被覆盖
```

Agent 的 SYSTEM_PROMPT 不含任何字段级指令——全凭 Schema 的 `description`、`type`、`standard_values` 驱动。

#### Phase 5 — 输出校验

对最终 DataFrame 再次执行 Schema 校验，所有违规输出 `!!` 警告。

### Step 4 — 质量报告

两个核心指标：

| 指标 | 计算方式 | 适用字段 |
|------|---------|---------|
| 完整度 `completeness_pct` | 非空行数 ÷ 总行数 | 所有字段 |
| 合规率 `compliance_pct` | 值在 `standard_values` 内的行数 ÷ 总行数 | 有标准值定义的字段 |

---

## LLM 输出容错机制

LLM 输出可能包含 markdown 包裹、尾逗号、缺字段等问题。代码做了三层防御：

1. **JSON 解析容错**：剥离 ```json 标记 → 直接解析 → 失败则清除尾逗号重试
2. **结构归一化**：对照 Schema，确保每个字段都有 `{"map": {...}}`，缺的补空
3. **类型+范围校验**：Pipeline 在运行过程中对每个字段值做类型、标准值、范围检查

---

## 控制台输出格式

```
========================================================
  [1/4]  生成脏数据
--------------------------------------------------------
  >> 生成 200 行 -> data/super_dirty_data.csv

========================================================
  [2/4]  自动生成规则 (AI 扫描)
--------------------------------------------------------
  >> 扫描唯一值...
  >> 生成映射规则...
  (LLM 流式输出)
   OK 规则已保存 (6 字段) -> data/auto_rules.json

========================================================
  [3/4]  执行 ETL 清洗
--------------------------------------------------------
  >> 规则清洗 (200 行)...
     规则清洗完成
  >> 推理: dept_name='妇科' -> gender='女'
   OK 应用 10 条 AI 推理规则
  >> Agent 清洗 (18/200 行, 10 并发)...
     Agent 清洗完成 (调用 18 次)
     清洗结果 -> output/final_cleaned.csv

========================================================
  [4/4]  生成质量报告
--------------------------------------------------------
     整体完整度: 92.0%
  >> 各字段详情:
     gender: 完整度=98.5%, 合规率=98.5%
     age: 完整度=73.5%
     ...
     清洗结果 -> output/final_cleaned.csv
     质量报告 -> output/quality_report.json

========================================================
  完成
  耗时: 45.3s
========================================================
```

| 符号 | 含义 |
|------|------|
| `>>` | 正在进行的操作 |
| `OK` | 操作完成 |
| `!!` | 警告或异常 |

---

## 配置

编辑 `config.py`：

```python
API_KEY = "sk-your-api-key"
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL   = "deepseek-v4-flash"
```

`run.py` 中可调整的参数：

```python
pipeline = ETLPipeline(
    schema_path,
    API_KEY,
    skip_agent=False,      # True=跳过 Agent，只用规则
    rules_path=rules_path,
    api_url=API_URL,
    model=MODEL,
    max_workers=10,        # Agent 并发数
    verbose=False,         # True=打印 Agent 流式输出（调试用）
)
```

---

## Schema 定义

编辑 `data/standard_schema.json` 来控制清洗目标——这是唯一的清洗指引来源：

```json
{
  "fields": [
    {
      "name": "gender",
      "type": "string",
      "description": "性别",
      "standard_values": ["男", "女", "未知"]
    },
    {
      "name": "age",
      "type": "integer",
      "description": "年龄（岁），范围0-120",
      "min": 0,
      "max": 120
    },
    {
      "name": "dept_name",
      "type": "string",
      "description": "科室名称",
      "standard_values": ["内科", "外科", "儿科", "妇科", "急诊科"]
    },
    {
      "name": "drug_name",
      "type": "string",
      "description": "药品通用名（去除剂型后缀）"
    }
  ]
}
```

支持的字段属性：

| 属性 | 作用 | 示例 |
|------|------|------|
| `type` | 数据类型 | `"string"` / `"integer"` |
| `description` | **清洗指引**：描述字段的目标格式 | `"药品通用名（去除剂型后缀）"` |
| `standard_values` | 允许值列表 | `["男","女","未知"]` |
| `min`/`max` | 数值范围 | `0`/`120` |

---

## 运行

```bash
# 1. 编辑 config.py 配置 API

# 2. 重跑前清理旧产物（可选）
rmdir /s output
del data\super_dirty_data.csv data\auto_rules.json

# 3. 运行
python run.py
```

---

## 各模块职责边界

| 模块 | 做什么 | 不做什么 |
|------|--------|---------|
| `RuleCleaner` | 查表替换 + 年龄整数校验 | 不做语义理解、不做跨字段推断 |
| `RuleGenerator` | 1 次 API 调用生成映射+推理规则 | 不处理具体行数据 |
| `LLMCleaner` | 语义理解、模糊值处理 | 不存储状态、不做批处理 |
| `ETLPipeline` | 编排五阶段：规则→推理→校验→Agent→输出 | 不负责数据持久化、不负责重试 |
| `QualityReporter` | 统计完整度/合规率 | 不修改数据、不做清洗 |
| `logger` | 格式化控制台输出（GBK 安全） | 不参与业务逻辑 |

---

## 耗时预估

| 阶段 | 耗时 | 说明 |
|------|------|------|
| Step 1 造脏数据 | 毫秒 | 纯本地 |
| Step 2 生成规则 | 2-5 秒 | 1 次 API 调用 |
| P1 规则清洗 | 毫秒 | 本地查表 |
| P2 AI 推理 | 微秒 | 直接遍历 |
| P3 Schema 校验 | 毫秒 | 本地检查 |
| P4 Agent 清洗 | `(需处理行数 ÷ max_workers) × 单次 2-5s` | 主要耗时 |
| Step 4 质量报告 | 毫秒 | 本地统计 |

---

## 关键技术决策

| 决策 | 选型 | 原因 |
|------|------|------|
| 清洗策略 | 规则 + AI推理 + Schema校验 + Agent | 规则解决确定性脏值，AI推理解决跨字段关系，校验确保合规，Agent处理剩余模糊值 |
| 规则生成 | AI 一次性输出映射+推理规则 | 无需代码反向推理，零噪音干扰 |
| Prompt 设计 | Schema 驱动，零硬编码 | 无需修改 Prompt，改 Schema 即改行为 |
| LLM 输出容错 | 尾逗号清洗 + markdown剥离 + 结构归一化 | 保证不同 LLM 的输出都能被正确解析 |
| 并发模型 | `ThreadPoolExecutor` | API 调用是 I/O 密集型，多线程即可 |
| 终端兼容 | `safe_print()` 兜底 GBK 编码 | Windows 中文终端可正常显示所有字符 |
