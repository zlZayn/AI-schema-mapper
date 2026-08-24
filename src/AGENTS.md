# src/ — 规则层

继承根规则，见 [../AGENTS.md](../AGENTS.md)。

src/ 特有约束：
- LLM 调用模块放 src/llm/，本地执行模块放 src/local/，不混放
- 新模块 / 改导出必须同步 [README.md](README.md) 文件索引
- API Key 与真实数据不得写进代码或提交