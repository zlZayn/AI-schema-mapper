# Schema Mapper

[![CI](https://github.com/zlZayn/AI-schema-mapper/actions/workflows/ci.yml/badge.svg)](https://github.com/zlZayn/AI-schema-mapper/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

基于 LLM 的智能数据清洗流水线，通过"AI 生成规则 + 本地执行"的架构，实现极低 Token 消耗的高效数据清洗。

## 核心特性

- **极低 Token 消耗**: AI 仅用于生成规则，实际清洗由本地代码执行
- **Schema 驱动**: 通过 JSON Schema 定义清洗目标，零硬编码
- **分层架构**: 清晰的 LLM 层与本地层分离，职责明确
- **可扩展**: 模块化设计，易于添加新的清洗规则或处理逻辑

## 快速开始

### 环境要求

- Python >= 3.11（项目锁定 3.12.10，见 `.python-version`）
- uv（依赖与运行环境管理，安装见 https://docs.astral.sh/uv/）

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置 API

编辑 `config.py`:

```python
API_KEY = "your-api-key"
API_BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash"
```

### 3. 运行

```bash
uv run python run.py            # 执行全流程（使用缓存）
uv run python run.py --no-cache # 强制重新调用 LLM，不使用缓存
```

输出文件:
- `output/final_cleaned.csv` - 清洗后的数据
- `output/quality_report.json` - 质量报告

运行结束时会输出 API 费用汇总（token 消耗和成本）。

## 项目结构

```
AI-schema-mapper/
├── docs/                          # 设计文档
│   └── ARCHITECTURE.md            # 架构设计文档
├── src/                           # 源代码
│   ├── llm/                       # LLM 层: 调用 API 生成规则
│   │   ├── rule_generator.py      # 第一轮: 生成业务映射规则
│   │   └── rule_refiner.py        # 第二轮: 生成整理规则(可选)
│   ├── local/                     # 本地层: 零 Token 执行
│   │   ├── rule_mapper.py         # 查表替换清洗
│   │   ├── final_polisher.py      # 最终整理
│   │   ├── quality_reporter.py    # 质量报告
│   │   └── logger.py              # 日志工具
│   ├── cache.py                   # 规则缓存（fingerprint + schema_hash）
│   ├── cost_tracker.py            # API 费用追踪
│   ├── data_generator.py          # 测试数据生成
│   └── etl_pipeline.py            # 流程编排器
├── data/                          # 数据目录
│   ├── standard_schema.json       # Schema 定义
│   ├── super_dirty_data.csv       # 输入脏数据
│   ├── auto_rules.json            # 生成的规则(自动) `[AI生成]`
│   ├── refinement_rules.json      # 整理规则(自动) `[AI生成]`
│   └── .rule_cache.json           # 规则缓存文件（自动生成）
├── output/                        # 输出目录
│   ├── final_cleaned.csv          # 清洗结果
│   └── quality_report.json        # 质量报告
├── config.py                      # 配置文件
├── config.example.py              # 配置模板
├── run.py                         # 入口脚本
├── AGENTS.md                      # 维护索引（开发者/维护者入口）
├── pyproject.toml                 # 依赖与元数据（uv）
├── uv.lock                        # 依赖锁文件
├── README.md                      # 本文档
└── WORKFLOW.md                    # 完整工作流程
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
| `etl_pipeline.py` | `[本地]` | 协调各模块执行 | 无 |

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

## 缓存机制

规则缓存基于两个维度判断是否命中：
- **fingerprint**: 各列唯一值排序后哈希（数据不变 → 指纹不变）
- **schema_hash**: Schema 文件内容哈希（Schema 不变 → hash 不变）

两者都匹配时直接复用缓存，跳过 LLM 调用。缓存文件：`data/.rule_cache.json`

## 费用追踪

每次 API 调用后自动记录 token 消耗，运行结束时输出费用汇总。定价基于 DeepSeek API（输入 1.0 元/百万 tokens，输出 2.0 元/百万 tokens）。

## 配置参数

`run.py` 中的可调参数:

```python
pipeline = ETLPipeline(
    schema_path="data/standard_schema.json",
    api_key=API_KEY,
    skip_llm_refinement=False,  # True=跳过第二轮 LLM
    rules_path="data/auto_rules.json",
    base_url=API_BASE_URL,
    model=MODEL,
    verbose=False,              # True=打印详细日志
)
```

## 了解更多

- [架构设计](docs/ARCHITECTURE.md) - 设计决策、Token 优化、扩展指南
- [维护索引](AGENTS.md) - 开发者/维护者入口：规则、命令、文档地图
- [WORKFLOW.md](WORKFLOW.md) - 完整工作流程、决策说明

## License

MIT

---

## 许可

- 本仓基于 [MIT 许可](LICENSE) 发布。

## 贡献

- 本仓为个人项目；问题与建议请走 [Issues](https://github.com/zlZayn/AI-schema-mapper/issues)。

维护者文档地图 → 见 [AGENTS.md](AGENTS.md)。
