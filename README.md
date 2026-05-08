# ETL Agent - 医疗数据智能清洗系统

基于 LLM 的智能 ETL 清洗流水线，通过"AI 生成规则 + 本地执行"的架构，实现极低 Token 消耗的高效数据清洗。

## 核心特性

- **极低 Token 消耗**: AI 仅用于生成规则，实际清洗由本地代码执行
- **Schema 驱动**: 通过 JSON Schema 定义清洗目标，零硬编码
- **分层架构**: 清晰的 LLM 层与本地层分离，职责明确
- **可扩展**: 模块化设计，易于添加新的清洗规则或处理逻辑

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API

编辑 `config.py`:

```python
API_KEY = "your-api-key"
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-flash"
```

### 3. 运行

```bash
python run.py
```

输出文件:
- `output/final_cleaned.csv` - 清洗后的数据
- `output/quality_report.json` - 质量报告

## 项目结构

```
etl-agent/
├── src/                          # 源代码
│   ├── llm/                      # LLM 层: 调用 API 生成规则
│   │   ├── rule_generator.py     # 第一轮: 生成业务映射规则
│   │   └── rule_refiner.py       # 第二轮: 生成整理规则(可选)
│   ├── local/                    # 本地层: 零 Token 执行
│   │   ├── rule_mapper.py        # 查表替换清洗
│   │   ├── final_polisher.py     # 最终整理
│   │   ├── quality_reporter.py   # 质量报告
│   │   └── logger.py             # 日志工具
│   └── pipeline.py               # 流程编排器
├── data/                         # 数据目录
│   ├── standard_schema.json      # Schema 定义
│   ├── super_dirty_data.csv      # 输入脏数据
│   ├── auto_rules.json           # 生成的规则(自动) `[AI生成]`
│   └── refinement_rules.json     # 整理规则(自动) `[AI生成]`
├── output/                       # 输出目录
│   ├── final_cleaned.csv         # 清洗结果
│   └── quality_report.json       # 质量报告
├── config.py                     # 配置文件
├── run.py                        # 入口脚本
├── requirements.txt              # 依赖
├── README.md                     # 本文档
└── ARCHITECTURE.md               # 架构设计文档
```

## 架构说明

### 数据流

脏数据

↓

**Step 1**: LLM 生成业务规则 `[AI]` → `auto_rules.json` `[AI生成]`

↓

**Step 2**: 本地规则清洗 `[本地]` → 查表替换

↓

**Step 3**: 本地跨字段推理 `[本地]` → 基于规则推断

↓

**Step 4**: LLM 生成整理规则 `[AI, 可选]` → `refinement_rules.json` `[AI生成]`

↓

**Step 5**: 本地整理清洗 `[本地]` → 查表替换

↓

**Step 6**: 本地最终整理 + 质量报告 `[本地]` → `final_cleaned.csv` + `quality_report.json`

**标签说明**：
- `[本地]` = 本地代码执行，零 Token 消耗
- `[AI]` = 调用 LLM API，消耗 Token
- `[AI, 可选]` = 可选的 AI 调用，可跳过
- `[AI生成]` = 该文件由 AI 生成

### 模块职责

| 模块 | 类型 | 职责 | API 调用 |
|------|------|------|----------|
| `llm/rule_generator.py` | `[AI]` | 分析数据分布，生成字段映射规则 | 1次 |
| `llm/rule_refiner.py` | `[AI]` | 分析残余问题，生成整理规则 | 0-1次 |
| `local/rule_mapper.py` | `[本地]` | 执行规则映射，查表替换 | 无 |
| `local/final_polisher.py` | `[本地]` | 最终格式整理 | 无 |
| `local/quality_reporter.py` | `[本地]` | 生成质量报告 | 无 |
| `pipeline.py` | `[本地]` | 协调各模块执行 | 无 |

## Schema 定义

编辑 `data/standard_schema.json` 定义清洗目标:

```json
{
  "fields": [
    {
      "name": "gender",
      "type": "string",
      "description": "性别。null表示缺失",
      "standard_values": ["男", "女"]
    },
    {
      "name": "age",
      "type": "integer",
      "description": "年龄（岁）",
      "min": 0,
      "max": 120
    }
  ]
}
```

字段属性:
- `name`: 字段名
- `type`: 数据类型 (`string`/`integer`)
- `description`: 字段描述，用于指导 AI 清洗
- `standard_values`: 标准值列表(可选)
- `min`/`max`: 数值范围(可选)

## 配置参数

`run.py` 中的可调参数:

```python
pipeline = ETLPipeline(
    schema_path="data/standard_schema.json",
    api_key=API_KEY,
    skip_llm_refinement=False,  # True=跳过第二轮 LLM
    rules_path="data/auto_rules.json",
    api_url=API_URL,
    model=MODEL,
    verbose=False,              # True=打印详细日志
)
```

## 了解更多

- [ARCHITECTURE.md](ARCHITECTURE.md) - 架构设计、Token优化、扩展指南
- [ETL_AGENT_WORKFLOW.md](ETL_AGENT_WORKFLOW.md) - 完整工作流程、决策说明

## License

MIT
