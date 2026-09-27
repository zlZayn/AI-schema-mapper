# Schema Mapper — 维护索引

## 全局规则
- 架构与数据流 → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 源码职责 / 变更影响路由 → [src/README.md](src/README.md)；子目录规则 → [src/AGENTS.md](src/AGENTS.md)
- 决策记录 → [.agents/notes/](.agents/notes/)，必须含替代方案
- 文档双件职责分离：AGENTS 只写规则、README 只写是什么/怎么改
- 文档动过就跑链接校验（maintenance-flow 技能 check-links.py）

## 常用命令（uv 管理，Python 3.12.10）
- `uv sync` · `uv run python run.py`（全流程/用缓存）· `uv run python run.py --no-cache`（强制调用 LLM）
- `uv run ruff check .` — Lint（ruff 默认规则集，列宽默认 88）
- `uv run ruff format .` — 格式化（`--check` 只看不改）

## 验证快照（上次实际跑过）
- Ruff 0.16.9（dev 依赖组）: `uv run ruff check .` 0 发现 · `uv run ruff format --check .` 全绿（2026-09-27）
- pytest 9.1.1（dev 依赖组）: no tests ran（项目无 tests/ 目录，exit 5）
- 冒烟导入 `uv run python -c "from src.etl_pipeline import ETLPipeline"`: ok

## 待办
- [ ] 补 tests/ 目录与首组用例

## 活跃坑
- config.py 含真实 API Key，已被 .gitignore 排除：勿提交、勿外传
- 无测试基线：改 local/ 清洗逻辑只能跑全流程验证

## 文档地图
- 架构 → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · 流程 → [WORKFLOW.md](WORKFLOW.md) · 介绍 → [PROJECT_INTRO.md](PROJECT_INTRO.md)