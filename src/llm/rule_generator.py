"""Auto-generate cleaning rules by scanning data and asking AI to produce mappings."""

import json
import re
from typing import ClassVar

import pandas as pd
from openai import OpenAI

from src.cache import fingerprint, load_cache, save_cache, schema_hash
from src.cost_tracker import record
from src.local.logger import ok, safe_print, step

GENERATOR_PROMPT = """根据 Schema 定义和你的医学知识，为以下数据生成清洗规则。

【Schema 定义 — 每个字段的描述、类型、允许值、范围已列出】
{target_info}

【输出格式】
```json
{{
  "gender":       {{"map": {{"脏值": "标准值", ...}}}},
  "age":          {{"map": {{"脏值": 标准值, ...}}}},
  "dept_name":    {{"map": {{"脏值": "标准值", ...}}}},
  "drug_name":    {{"map": {{"脏值": "标准值", ...}}}},
  "diagnosis_code": {{"map": {{"脏值": "标准值", ...}}}},
  "inference":    {{
    "dept_name": {{"source值": {{"target字段": "推断值"}}}}
  }}
}}
```

【要求】
- Schema 的 description、type、standard_values、range 定义了每个字段的清洗目标，你的输出必须遵循
- 利用你的医学知识，将所有能确定映射的脏值→标准值放入 map
- 如果你能确定稳定的跨字段关系（如某科室→推断性别），放入 inference
- 把你能力范围内能确定的都放入，不要遗漏
- 不确定的不要放入
- 只输出 JSON

【各字段唯一值】
{unique_values}"""


class RuleGenerator:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-v4-flash",
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    # Columns that are pass-through and should not affect the cache fingerprint
    PASS_THROUGH_COLUMNS: ClassVar[set[str]] = {"patient_id"}

    def scan_unique_values(self, csv_path: str) -> dict:
        df = pd.read_csv(csv_path)
        return {
            col: df[col].dropna().astype(str).unique().tolist() for col in df.columns
        }

    def generate_rules(
        self, unique_values: dict, schema_path: str | None = None
    ) -> dict:
        # Build target constraints from schema
        target_info = "无附加约束"
        if schema_path:
            with open(schema_path, encoding="utf-8") as f:
                schema = json.load(f)
            lines = []
            for field in schema.get("fields", []):
                parts = [f"- {field['name']}: type={field.get('type', 'string')}"]
                sv = field.get("standard_values")
                if sv:
                    parts.append(f" 允许值={sv}")
                if field.get("min") is not None:
                    parts.append(f" 范围=[{field['min']}, {field['max']}]")
                lines.append("".join(parts))
            target_info = "\n".join(lines)

        prompt = GENERATOR_PROMPT.format(
            target_info=target_info,
            unique_values=json.dumps(unique_values, ensure_ascii=False, indent=2),
        )
        step("生成映射规则...")
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            stream=True,
            stream_options={"include_usage": True},
        )

        full_content = ""
        usage = None
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            text = delta.content if delta and delta.content else ""
            if text:
                safe_print(text)
                full_content += text
            if chunk.usage:
                usage = chunk.usage

        print()
        if usage:
            record("rule_generator", usage.prompt_tokens, usage.completion_tokens)
        return self._extract_json(full_content)

    def run(
        self,
        csv_path: str,
        output_path: str,
        schema_path: str | None = None,
        cache_path: str | None = None,
    ) -> dict:
        step("扫描唯一值...")
        unique_values = self.scan_unique_values(csv_path)

        # Check cache
        if cache_path and schema_path:
            fp = fingerprint(unique_values, exclude_columns=self.PASS_THROUGH_COLUMNS)
            sh = schema_hash(schema_path)
            cached = load_cache(cache_path, sh, fp)
            if cached:
                ok("缓存命中，跳过 LLM 调用")
                rules = cached.get("auto_rules", cached)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(rules, f, ensure_ascii=False, indent=2)
                ok(f"规则已保存 ({len(rules)} 字段) -> {output_path}")
                return rules

        rules = self.generate_rules(unique_values, schema_path)
        rules = self._normalize_structure(rules, schema_path)

        # Save to cache
        if cache_path and schema_path:
            save_cache(cache_path, sh, fp, {"auto_rules": rules})

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        ok(f"规则已保存 ({len(rules)} 字段) -> {output_path}")
        return rules

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract and parse JSON from LLM output, handling markdown and trailing commas."""
        if not text:
            return {}
        text = text.replace("```json", "").replace("```", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            return {}
        raw = text[start:end]
        # Direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Fallback: strip trailing commas
        cleaned = re.sub(r",\s*}", "}", raw)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _normalize_structure(rules: dict, schema_path: str | None = None) -> dict:
        """Ensure every Schema field has a map entry and inference is structured.

        Supports both formats:
        - LLM output: {"gender": {"M": "男", ...}, ...}
        - Expected: {"gender": {"map": {"M": "男", ...}}, ...}
        """
        if not isinstance(rules, dict):
            return {}

        # Convert LLM output format to expected format
        normalized = {}
        for key, value in rules.items():
            if key == "inference":
                normalized[key] = value if isinstance(value, dict) else {}
            elif isinstance(value, dict):
                if "map" in value:
                    # Already in correct format
                    normalized[key] = value
                else:
                    # Convert LLM format {"脏值": "标准值"} to {"map": {...}}
                    normalized[key] = {"map": value}
            else:
                normalized[key] = {"map": {}}

        # Ensure all schema fields have an entry
        if schema_path:
            with open(schema_path, encoding="utf-8") as f:
                schema = json.load(f)
            expected = {
                f["name"] for f in schema.get("fields", []) if f["name"] != "patient_id"
            }
            for field in expected:
                if field not in normalized:
                    normalized[field] = {"map": {}}

        if "inference" not in normalized:
            normalized["inference"] = {}

        return normalized
