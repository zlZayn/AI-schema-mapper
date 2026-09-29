# 决策：架构文档迁入 docs/ 与文档结构标准化（2026-08-24）

状态：生效

## 问题
- 根目录散放 ARCHITECTURE.md，无 docs/、无根 AGENTS.md、无 .agents/notes/
- README 命令与结构描述与实际不符（pip install requirements.txt 但该文件不存在、pipeline.py 实际为 etl_pipeline.py、ARCHITECTURE 链接指向根目录）
- Agent 无自动注入的维护规则，文档无链接校验兜底

## 决策
- 架构设计唯一位置为 docs/ARCHITECTURE.md（git mv，保留历史）
- 根 AGENTS.md 为维护仪表盘（规则/命令/验证快照/待办/活跃坑/文档地图）
- src/ 建立双件（AGENTS.md 规则层 + README.md 文档层）；data/、output/ 不建
- README 命令与结构对齐实际（uv sync / uv run python run.py）

## 替代方案（强制）
- 方案 A：ARCHITECTURE.md 留在根目录：违反 docs/ 统一规范，根目录继续膨胀；否决
- 方案 B：只补缺失文档、不移动 ARCHITECTURE.md：无法满足结构标准化目标，架构文档位置不统一；否决
- 方案 C：tests/、data/、output/ 全部建立双件：数据目录无维护规则价值、双件泛滥，且 tests/ 当前不存在；否决

## 影响
- git 跟踪路径变更：ARCHITECTURE.md → docs/ARCHITECTURE.md（rename 已暂存，未提交）
- 全项目 markdown 链接修正 2 处（README 1 处 + ARCHITECTURE 自身 1 处）
- 后续文档改动需跑 check-links.py 验证链接