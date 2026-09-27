"""LLM rule refiner: analyze remaining dirty values after first pass and generate refinement rules.

This is the second AI call in the pipeline. Its job is minimal:
- Look at values that survived the first rule-based cleaning
- Decide how to normalize them (missing values, uncertain values, format issues)
- Output simple mapping rules for local code to apply

The AI has freedom to decide WHAT to map, but must follow the output format.
"""

import json
import re

import pandas as pd
from openai import OpenAI

from src.cache import fingerprint, load_cache, save_cache, schema_hash
from src.cost_tracker import record
from src.local.logger import ok, safe_print, step

REFINER_PROMPT = """你是一个数据整理专家。你的任务是分析经过第一轮清洗后仍然"有问题"的数据值，并生成整理规则。

【背景】
- 数据已经经过第一轮规则清洗，大部分业务映射已完成
- 你现在看到的是"残余问题"：各种缺失表示、不确定值、格式问题
- 你的目标是把它们归类整理，让数据更整洁统一

【任务】
分析每个字段的残余值，生成归类规则：

1. **missing_values**: 各种"缺失"的表示 → 统一映射为 null
   - 比如：空字符串、"null"、"N/A"、"-" 等明显表示"没有数据"的值

2. **uncertain_values**: 各种"不确定"的表示 → 统一映射为一个标准值（如"未知"）
   - 比如："???"、"不详"、"保密"、"待确认" 等表示"有数据但不确定"的值

3. **type_fixes**: 类型格式问题 → 修复为正确格式
   - 比如：数字字符串去除小数（"35.0" → 35）
   - 比如：字符串去除前后空格（" 男 " → "男"）

【重要原则】
- 不要硬编码具体值，根据实际数据灵活判断
- 只处理"整理归类"，不处理业务映射（如科室名称转换已在第一轮完成）
- 不确定的字段可以留空，让代码保持原值

【输出格式】
必须输出合法JSON，格式如下：
```json
{
  "missing_values": {
    "字段名": {"原始值1": null, "原始值2": null},
    ...
  },
  "uncertain_values": {
    "字段名": {"原始值1": "归类后的值", "原始值2": "归类后的值"},
    ...
  },
  "type_fixes": {
    "字段名": {"remove_decimals": true, "trim_whitespace": true},
    ...
  }
}
```

只输出JSON，不要任何解释文字。"""


class LLMRuleRefiner:
    """Refine rules by analyzing remaining dirty values after first pass."""

    def __init__(
        self,
        schema_path: str,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        verbose: bool = False,
        cache_path: str | None = None,
    ):
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)
        self.client = OpenAI(
            api_key=api_key, base_url=base_url or "https://api.deepseek.com/v1"
        )
        self.model = model or "deepseek-v4-flash"
        self.verbose = verbose
        self.cache_path = cache_path
        self._schema_hash = schema_hash(schema_path) if cache_path else None

    def generate_refinement_rules(
        self, remaining_values: dict, output_path: str
    ) -> dict:
        """Generate refinement rules by analyzing remaining dirty values.

        Args:
            remaining_values: Dict of field_name -> list of unique remaining values
            output_path: Where to save the refinement rules

        Returns:
            Refinement rules dict
        """
        step("生成整理规则 (AI 分析残余值)...")

        # Check cache
        if self.cache_path and self._schema_hash:
            fp = fingerprint(remaining_values)
            cached = load_cache(self.cache_path, self._schema_hash, fp)
            if cached:
                rules = cached.get("refinement_rules", cached)
                if rules:
                    ok("整理规则缓存命中，跳过 LLM 调用")
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(rules, f, ensure_ascii=False, indent=2)
                    ok(f"整理规则已保存 -> {output_path}")
                    return rules

        user_prompt = (
            f"Schema:\n{json.dumps(self.schema, ensure_ascii=False)}\n\n"
            f"第一轮清洗后剩余的'问题值'（各字段唯一值）：\n"
            f"{json.dumps(remaining_values, ensure_ascii=False, indent=2)}\n\n"
            f"请生成整理规则JSON。"
        )

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": REFINER_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
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
                    if self.verbose:
                        safe_print(text)
                    full_content += text
                if chunk.usage:
                    usage = chunk.usage

            if self.verbose:
                print()

            if usage:
                record("rule_refiner", usage.prompt_tokens, usage.completion_tokens)

            rules = self._extract_json(full_content)
            if rules:
                # Save to cache
                if self.cache_path and self._schema_hash:
                    save_cache(
                        self.cache_path,
                        self._schema_hash,
                        fp,
                        {"refinement_rules": rules},
                    )
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(rules, f, ensure_ascii=False, indent=2)
                ok(f"整理规则已保存 -> {output_path}")
                return rules
            else:
                safe_print(
                    "  [Warning] Failed to parse refinement rules, using empty rules"
                )
                return {}

        except Exception as e:  # noqa: BLE001 — 覆盖流式调用与落盘，收窄会漏掉非 OSError 的 SDK 异常
            safe_print(f"\n  [LLM] API call failed: {e}")
            return {}

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract and parse JSON from LLM output."""
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
        cleaned = re.sub(r",\s*}", "}", raw)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def extract_remaining_values(df: pd.DataFrame, schema: dict) -> dict:
        """Extract unique values from columns that still have issues.

        Args:
            df: DataFrame after first pass of cleaning
            schema: Schema definition

        Returns:
            Dict of field_name -> list of unique problematic values
        """
        remaining = {}
        for field in schema.get("fields", []):
            name = field["name"]
            if name not in df.columns:
                continue

            col = df[name]
            unique_vals = col.dropna().unique().tolist()

            # Filter to values that might need refinement
            # (nulls, empty strings, or values not in standard_values)
            std_vals = field.get("standard_values")
            problematic = []

            for val in unique_vals:
                str_val = str(val).strip()
                # Include empty/null-like values
                if (
                    str_val
                    in (
                        "",
                        "null",
                        "None",
                        "nan",
                        "NaN",
                        "N/A",
                        "n/a",
                        "-",
                        "/",
                    )
                    or std_vals
                    and str_val not in std_vals
                ):
                    problematic.append(str_val)
                # Include values with whitespace issues
                elif str_val != str(val):
                    problematic.append(str(val))

            if problematic:
                remaining[name] = list(set(problematic))

        return remaining
