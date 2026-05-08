"""Final polishing layer: normalize data using AI-generated JSON mapping rules.

This module provides a lightweight, token-efficient way to standardize cleaned data:
- AI generates mapping rules once (minimal tokens)
- Local Python applies rules via dictionary lookup (zero tokens)
- Ensures Schema compliance and consistent formatting
"""

import json
import pandas as pd
from typing import Any
from src.local.logger import step, ok


class FinalPolisher:
    """Apply final polish rules to ensure data consistency and Schema compliance."""

    # Default normalization rules (can be overridden by AI-generated rules)
    DEFAULT_RULES = {
        # Normalize missing/unknown values
        "missing_values": {
            "null": None,
            "": None,
            " ": None,
            "nan": None,
            "NaN": None,
            "NULL": None,
            "null": None,
            "None": None,
            "none": None,
            "N/A": None,
            "n/a": None,
            "-": None,
            "/": None,
        },
        # Normalize uncertain values to standard "未知"
        "uncertain_values": {
            "不详": "未知",
            "未填": "未知",
            "未填": "未知",
            "保密": "未知",
            "???": "未知",
            "?": "未知",
            "不确定": "未知",
            "待查": "未知",
            "待确认": "未知",
        },
        # Field-specific final mappings
        "field_mappings": {
            # Example: "gender": {"": "未知", "null": "未知"}
        },
        # Type formatting rules
        "type_format": {
            "integer": {"remove_decimals": True, "null_on_invalid": True},
            "string": {"strip_whitespace": True, "null_on_empty": True},
        },
    }

    def __init__(self, schema_path: str, polish_rules_path: str | None = None):
        """Initialize polisher with Schema and optional custom rules.

        Args:
            schema_path: Path to Schema JSON file
            polish_rules_path: Path to AI-generated polish rules (optional)
        """
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)

        self.rules = self._load_rules(polish_rules_path)
        self._build_field_lookup()

    def _load_rules(self, rules_path: str | None) -> dict:
        """Load polish rules from file or use defaults."""
        if rules_path:
            with open(rules_path, encoding="utf-8") as f:
                custom_rules = json.load(f)
            # Merge with defaults
            merged = self.DEFAULT_RULES.copy()
            merged.update(custom_rules)
            return merged
        return self.DEFAULT_RULES.copy()

    def _build_field_lookup(self):
        """Build quick lookup for field definitions."""
        self.field_defs = {}
        for field in self.schema.get("fields", []):
            self.field_defs[field["name"]] = field

    def polish(self, row: dict) -> dict:
        """Apply polish rules to a single row.

        Args:
            row: Dictionary of field values

        Returns:
            Polished row dictionary
        """
        result = {}

        for field_name, value in row.items():
            field_def = self.field_defs.get(field_name, {})
            dtype = field_def.get("type", "string")

            # Step 1: Normalize missing/uncertain values
            value = self._normalize_missing(value)

            # Step 2: Apply field-specific mappings
            value = self._apply_field_mapping(field_name, value)

            # Step 3: Type-specific formatting
            value = self._format_by_type(value, dtype, field_def)

            # Step 4: Ensure Schema compliance
            value = self._ensure_compliance(value, field_def)

            result[field_name] = value

        return result

    def _normalize_missing(self, value: Any) -> Any:
        """Normalize various missing value representations."""
        if value is None:
            return None

        str_val = str(value).strip()

        # Check missing values map
        if str_val in self.rules["missing_values"]:
            return self.rules["missing_values"][str_val]

        # Check uncertain values map
        if str_val in self.rules["uncertain_values"]:
            return self.rules["uncertain_values"][str_val]

        return value

    def _apply_field_mapping(self, field_name: str, value: Any) -> Any:
        """Apply field-specific final mappings."""
        if value is None:
            return None

        field_maps = self.rules.get("field_mappings", {})
        if field_name in field_maps:
            str_val = str(value).strip()
            return field_maps[field_name].get(str_val, value)

        return value

    def _format_by_type(self, value: Any, dtype: str, field_def: dict) -> Any:
        """Apply type-specific formatting."""
        if value is None:
            return None

        type_rules = self.rules.get("type_format", {}).get(dtype, {})

        if dtype == "integer":
            return self._format_integer(value, type_rules)
        elif dtype == "string":
            return self._format_string(value, type_rules)

        return value

    def _format_integer(self, value: Any, rules: dict) -> int | None:
        """Format integer value."""
        try:
            # Handle float strings like "35.0"
            if isinstance(value, str):
                if "." in value:
                    value = float(value)
                else:
                    value = int(value)
            elif isinstance(value, float):
                pass  # Will convert below
            elif not isinstance(value, int):
                raise ValueError

            # Remove decimals if configured
            if rules.get("remove_decimals", True):
                value = int(value)

            return value
        except (ValueError, TypeError):
            if rules.get("null_on_invalid", True):
                return None
            return value

    def _format_string(self, value: Any, rules: dict) -> str | None:
        """Format string value."""
        str_val = str(value).strip()

        # Strip whitespace if configured
        if rules.get("strip_whitespace", True):
            str_val = str_val.strip()

        # Null on empty if configured
        if rules.get("null_on_empty", True) and not str_val:
            return None

        return str_val

    def _ensure_compliance(self, value: Any, field_def: dict) -> Any:
        """Ensure value complies with Schema constraints."""
        if value is None:
            return None

        dtype = field_def.get("type", "string")
        std_vals = field_def.get("standard_values")

        # Check standard values
        if std_vals and value not in std_vals:
            # If not in standard values, try to normalize or set to None
            str_val = str(value)
            if str_val not in std_vals:
                # For gender, default to "未知" if invalid
                if field_def.get("name") == "gender":
                    return "未知"
                return None

        # Check range for integers
        if dtype == "integer":
            min_val = field_def.get("min")
            max_val = field_def.get("max")
            if min_val is not None and max_val is not None:
                try:
                    iv = int(value)
                    if not (min_val <= iv <= max_val):
                        return None
                except (ValueError, TypeError):
                    return None

        return value

    def polish_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Polish entire DataFrame.

        Args:
            df: Input DataFrame

        Returns:
            Polished DataFrame
        """
        step(f"最终整理 ({len(df)} 行)...")

        polished_rows = []
        for _, row in df.iterrows():
            polished_rows.append(self.polish(row.to_dict()))

        result_df = pd.DataFrame(polished_rows)
        ok("最终整理完成")

        return result_df

    def generate_polish_rules_prompt(self, unique_values: dict) -> str:
        """Generate a minimal prompt for AI to create polish rules.

        This is designed to use minimal tokens - AI only outputs JSON rules,
        not processed data. Uses unique values instead of full data.

        Args:
            unique_values: Dict of field_name -> list of unique values

        Returns:
            Prompt string for AI
        """
        return f"""根据以下Schema和各字段唯一值，生成最终整理规则JSON。

【Schema定义】
{json.dumps(self.schema, ensure_ascii=False, indent=2)}

【各字段唯一值（去重后）】
{json.dumps(unique_values, ensure_ascii=False, indent=2)}

【任务】
分析唯一值中的问题，生成polish规则JSON：
1. 识别各种缺失值表示（如 "nan", "NULL", "", "N/A" 等）→ 统一映射为 null
2. 识别不确定值（如 "不详", "保密", "???" 等）→ 统一映射为 "未知"
3. 字段特定映射（如 gender 的空值 → "未知"）
4. 类型格式化规则（如整数去除小数）

【输出格式】
```json
{{
  "missing_values": {{"nan": null, "NULL": null, "": null, ...}},
  "uncertain_values": {{"不详": "未知", "保密": "未知", ...}},
  "field_mappings": {{"gender": {{"": "未知"}}}},
  "type_format": {{"integer": {{"remove_decimals": true}}}}
}}
```

只输出JSON规则，不输出处理后的数据。"""
