# 决策：文档类名对齐实际代码，不重命名代码只改文档（2026-08-28）

已实施：是

## 问题
- README.md / docs/ARCHITECTURE.md 使用不存在的类名：LocalRuleMapper、LocalFinalPolisher、LLMRuleGenerator、LLMRowCleaner
- 代码实际类名：RuleCleaner（rule_mapper.py）、FinalPolisher（final_polisher.py）、RuleGenerator（rule_generator.py）
- 文档与代码的类名脱节，读者按文档找类必扑空

## 决策
- 只改文档：docs/ARCHITECTURE.md 18 处类名改为实际类名（commit cf80273），LLMRowCleaner 标注「早期架构，已移除」
- 不改代码：类名、导入路径、run.py 调用点保持原样
- 命名约定固化：文档中类名必须等于代码实际类名，新增模块须在 src/README.md 文件索引同时登记类名

## 替代方案（强制）
- 方案 A：重命名代码类统一命名（如 RuleCleaner → LocalRuleMapper）：牵动全部 import 与运行入口，项目无 tests/ 基线，回归验证成本高；收益仅为命名美观；否决
- 方案 B：直接删除过时的 LLMRowCleaner 不提：Token 对比表失去历史对照，读者会误认早期架构不存在；否决，改为显式标注「早期架构，已移除」

## 影响
- cf80273 仅动 docs/ARCHITECTURE.md（20+/20-），零代码变更
- 同批文档维护：4145e42 删除无引用的 main.py 脚手架；ecb393c 新增 `[dependency-groups] dev = ["pytest>=8.0"]`（PEP 735；本仓库无 tests/，pytest 仅为契约性验证入口）
- 后续文档改动类名须对照 src/README.md 登记表，跑链接校验兜底