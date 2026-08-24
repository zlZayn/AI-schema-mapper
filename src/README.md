# src/ — 源码手册

- 职责：LLM 规则生成 + 本地清洗执行链
- llm/ 目录 = AI 层（消耗 Token）；local/ 目录 = 本地层（零 Token）

文件索引（职责 / 关键导出 / 依赖）：
- cache.py：fingerprint + schema_hash 规则缓存；被 rule_generator、rule_refiner 依赖
- cost_tracker.py：API 费用追踪（record/reset/summary）；被 llm/ 与 run.py 依赖
- data_generator.py：生成测试脏数据（generate_dirty_data）；被 run.py 依赖
- etl_pipeline.py：流程编排器（ETLPipeline）；被 run.py 依赖；改签名必须同步 run.py 与根文档
- llm/rule_generator.py：第一轮业务映射规则（RuleGenerator）
- llm/rule_refiner.py：第二轮整理规则（LLMRuleRefiner，可选）
- local/rule_mapper.py：查表替换清洗（RuleCleaner）
- local/final_polisher.py：最终格式整理（FinalPolisher）
- local/quality_reporter.py：质量报告（QualityReporter）
- local/logger.py：日志工具（section/step/ok/warn/start_timer/done）

变更影响路由：
- 改导出 / 签名 → 同步根 [AGENTS.md](../AGENTS.md) 待办与活跃坑、[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) 契约描述
- 当前无 tests/：改清洗逻辑后建议 `uv run python run.py` 全流程冒烟

使用约束与工作偏好 → [AGENTS.md](AGENTS.md)