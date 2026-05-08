"""AI Agent cleaner using DeepSeek API for fuzzy, non-standard data."""

import json
import re
import requests
from src.logger import safe_print


SYSTEM_PROMPT = """你是一个医疗数据标准化专家。用你的医学知识清洗医疗脏数据，输出严格符合 Schema 的纯 JSON。

【核心原则】
- Schema 会随输入一起提供，每个字段的 description/type/standard_values/range 定义了清洗目标，你的输出必须严格遵循
- 利用行内所有字段的上下文做合理的跨字段推理
- 你具备完整的医学领域知识，能识别各种数据变体
- 不确定的字段输出 null，不要强行猜测

【输出要求】
- 输出包含所有 Schema 字段的合法 JSON
- 不要输出任何额外文字或标记"""


class LLMCleaner:
    def __init__(
        self,
        schema_path: str,
        api_key: str,
        api_url: str = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
        model: str = "mimo-v2-pro",
        verbose: bool = False,
    ):
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.verbose = verbose

    def clean(self, row_dict: dict) -> dict | None:
        user_prompt = (
            f"Schema:\n{json.dumps(self.schema, ensure_ascii=False)}\n\n"
            f"原始数据行:\n{json.dumps(row_dict, ensure_ascii=False)}\n\n"
            f"请输出标准化后的JSON。"
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "stream": True,
        }
        try:
            resp = requests.post(
                self.api_url, headers=headers, json=payload, timeout=120, stream=True
            )
            resp.raise_for_status()

            full_content = ""
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        if self.verbose:
                            safe_print(text)
                        full_content += text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

            if self.verbose:
                print()
            return self._extract_json(full_content)
        except Exception as e:
            safe_print(f"\n  [Agent] API call failed: {e}")
            return None

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract and parse JSON from LLM output, handling markdown and trailing commas."""
        if not text:
            return None
        text = text.replace("```json", "").replace("```", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            return None
        raw = text[start:end]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        cleaned = re.sub(r',\s*}', '}', raw)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None
