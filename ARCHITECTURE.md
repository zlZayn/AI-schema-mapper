# ETL Agent 架构设计

> 本文档面向开发者: 详细说明架构设计、Token 优化策略和扩展指南。普通用户请查看 [README.md](./README.md) 了解快速开始。

---

## 核心设计理念

### AI 做一次理解，代码做 N 次执行

**AI 层** `[AI]` (1-2 次 API 调用，极少 Token)
- Step 1: LLMRuleGenerator - 理解数据分布 → 生成业务映射规则
- Step 2: LLMRuleRefiner - 分析残余问题 → 生成整理规则（可选）

↓

**代码层** `[本地]` (纯本地，N 次执行，零 Token)
- LocalRuleMapper: 查表替换（毫秒级 × 所有行）
- 跨字段推理: 本地推理（零 Token）
- 整理规则应用: 本地应用 AI 生成的整理规则（零 Token）
- LocalFinalPolisher: 最终整理（零 Token）
- Schema 校验: 本地检查（零 Token）

**关键洞察**: 数据清洗是确定性的，不需要每行都调用 AI。AI 只需要理解**模式**（pattern），然后代码可以高效地应用这些模式。

---

## 五层架构

### 架构概览

Layer 1: 数据生成层 `[本地]`
- 生成模拟脏数据
- 输出: `super_dirty_data.csv`

↓

Layer 2: 规则生成层 `[AI]`
- 扫描唯一值（去重后几十到几百个）
- LLM 生成映射规则 + 跨字段推理规则
- Token: 极少（只传唯一值，不传完整数据）
- 输出: `auto_rules.json` `[AI生成]`

↓

Layer 3: 清洗执行层 `[本地]`
- Phase 1: LocalRuleMapper - 查表替换（毫秒级，零Token）
- Phase 2: 跨字段推断 - 本地推理（零Token）
- Phase 3: 整理规则应用 - 本地应用 AI 生成的整理规则（零Token）
- Phase 4: Schema 校验 - 本地检查（零Token）
- 输出: 清洗后的数据（中间状态）

↓

Layer 4: 最终整理层 `[本地]`
- 使用默认规则进行最终整理
- 统一缺失值表示、格式标准化
- 确保 Schema 合规性
- 输出: `final_cleaned.csv` `[最终]`

↓

Layer 5: 质量报告层 `[本地]`
- 统计完整度、合规率
- 输出: `quality_report.json`

### 模块命名规范

| 文件名 | 类型 | 职责 | API调用 |
|--------|------|------|---------|
| `llm/rule_generator.py` | `[AI]` | 扫描唯一值，生成业务映射规则 | 1次 |
| `llm/rule_refiner.py` | `[AI]` | 分析残余问题，生成整理规则 | 0-1次 |
| `local/rule_mapper.py` | `[本地]` | 查表替换，执行规则清洗 | 无 |
| `local/final_polisher.py` | `[本地]` | 最终整理，统一格式 | 无 |
| `local/quality_reporter.py` | `[本地]` | 统计完整度、合规率 | 无 |
| `local/logger.py` | `[本地]` | 日志输出工具 | 无 |
| `etl_pipeline.py` | `[本地]` | 协调各层执行 | 无 |

**命名规则**:
- `llm_` 前缀 = 调用 LLM API，消耗 Token `[AI]`
- `local_` 前缀 = 纯本地执行，零 Token `[本地]`

---

## Token 消耗详解

### 与传统方案对比

| 方案 | 数据量 | AI 调用次数 | 每次输入 | Token 消耗 | 说明 |
|------|--------|------------|---------|-----------|------|
| 传统方案 | 150行 | 150次 | 完整数据 | **极高** | 每行都调用 AI |
| 早期架构 | 150行 | 1次 + 30次 | 唯一值 + 单行 | **中等** | 规则生成1次，脏行逐行调用 |
| 当前架构 | 150行 | 1-2次 | 唯一值 | **极少** | 仅生成规则，全部本地执行 |

### 为什么 Token 消耗少？

**核心优化**: AI 从不处理完整数据集

| 阶段 | 输入数据 | 数据量 | Token 级别 |
|------|---------|--------|-----------|
| LLMRuleGenerator | 唯一值列表 | ~100个字符串 | 极少 `[AI]` |
| LLMRowCleaner | 单行数据 | ~200 tokens/行 | 中等 `[AI]` |
| LocalFinalPolisher | 唯一值列表 | ~50个字符串 | 极少 `[本地]` |
| 本地执行 | 完整数据集 | 150行 | **零 Token** `[本地]` |

**数学对比**（150行数据）:
- 传统方案: 150 × 200 = **30,000 tokens**
- ETL Agent: 500 + (30 × 200) = **6,500 tokens** (节省 78%)

### 实际测试数据（150行）

总 AI 调用次数: 1-2 次
- LLMRuleGenerator: 1 次（生成业务映射规则） `[AI]`
- LLMRuleRefiner: 0-1 次（生成整理规则，可选） `[AI, 可选]`

本地执行: 100% 的行 `[本地]`
- LocalRuleMapper: 150 行（查表替换）
- 跨字段推断: 150 行（本地计算）
- 整理规则应用: 150 行（本地执行）
- LocalFinalPolisher: 150 行（本地整理）
- Schema 校验: 150 行（本地检查）

---

## 数据隔离与安全

### 数据流隔离

原始数据 (CSV)
↓
LLMRuleGenerator `[AI]` → 唯一值列表 → AI
                              ↓
                         `auto_rules.json` `[AI生成]`
                              ↓
ETLPipeline `[本地]` ←───────────────┘
↓
├── LocalRuleMapper `[本地]`
├── 跨字段推断 `[本地]`
├── Schema 校验 `[本地]`
└── LocalFinalPolisher `[本地]`
    ↓
`final_cleaned.csv`

### AI 数据接触范围

| 组件 | 类型 | 接触数据 | 敏感信息暴露 |
|------|------|---------|-------------|
| LLMRuleGenerator | `[AI]` | 唯一值列表 | 低（去重后） |
| LLMRuleRefiner | `[AI]` | 唯一值列表 | 低（去重后，仅残余问题值） |
| LocalFinalPolisher | `[本地]` | 无（使用默认规则） | 无 |

---

## 扩展性设计

### 添加新的清洗层

```python
# 在 ETLPipeline.run() 中添加新阶段
final_df = pd.DataFrame(rule_results)

# Phase 3: 你的新清洗层
final_df = your_new_layer(final_df)

# Phase 4: LocalFinalPolisher
polisher = LocalFinalPolisher(self.schema_path)
final_df = polisher.polish_dataframe(final_df)
```

### 自定义 Polish 规则

```python
# 使用默认规则（零 AI 调用）
polisher = LocalFinalPolisher("schema.json")

# 或使用 LLM 生成规则（一次性，极少 Token）
polisher = LocalFinalPolisher("schema.json", "custom_polish_rules.json")
```

---

## 关键实现细节

### RuleMapper 的值保留策略

`local/rule_mapper.py` 中的清洗逻辑遵循以下优先级：

1. **映射表匹配**: 如果值在 AI 生成的映射表中，使用映射后的标准值
2. **标准值保留**: 如果值本身就是标准值（在 `standard_values` 列表中），保留原值
3. **无标准值列表字段**: 如果字段没有预定义 `standard_values`（如 `drug_name`），保留非空原值
4. **无效值**: 既不在映射表中也不是标准值的，设为 `None`

```python
# 示例行为
"甲硝唑片0.2g" → 映射表 → "甲硝唑片"          # 非标准值，映射为标准值
"甲硝唑片"     → 标准值检查 → "甲硝唑片"      # 已是标准值，保留
"无效药品"     → 无效值 → None               # 无效值，设为 None
```

### 为什么需要这个策略？

AI 生成的规则只包含**需要转换**的非标准值（如 `"甲硝唑片0.2g" → "甲硝唑片"`），不包含已经是标准值的映射（如 `"甲硝唑片" → "甲硝唑片"`）。如果没有值保留策略，标准值会被错误地映射为 `None`，导致数据丢失。

## 性能优化点

1. **规则缓存**: `auto_rules.json` `[AI生成]` 和 `refinement_rules.json` `[AI生成]` 可缓存复用
2. **架构升级**: 从"AI 逐行清洗"改为"AI 生成规则 + 本地执行"，AI 调用从 140+ 次降至 1-2 次
3. **提前过滤**: 仅传递唯一值给 AI，而非完整数据集
4. **本地优先**: 100% 的数据处理在本地完成，零 Token 消耗

---

## 文档职责说明

| 文档 | 目标读者 | 内容重点 |
|------|---------|---------|
| **README.md** | 普通用户 | 快速开始、配置、简要说明 |
| **ARCHITECTURE.md** | 开发者 | 架构细节、Token优化、扩展指南 |
| **ETL_AGENT_WORKFLOW.md** | 开发者/运维 | 完整工作流程、决策说明 |

---

## 总结

ETL Agent 通过**分层架构**、**命名规范**和**规则驱动**设计，实现了：

- **清晰的职责分离**: 文件名即知是否调用 API `[AI]` / `[本地]`
- **极低的 Token 消耗**: LLM 只处理去重后的唯一值和必要的脏行
- **高效的数据清洗**: 90%+ 的处理在本地完成
- **灵活的规则管理**: JSON 规则文件可人工编辑、版本控制
