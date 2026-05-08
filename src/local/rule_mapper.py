"""Rule-based cleaner with dynamically generated or static mappings."""

import json


class RuleCleaner:
    IMPORTANT_FIELDS = {"gender", "dept_name", "drug_name", "diagnosis_code", "age"}
    PASS_THROUGH_FIELDS = {"patient_id"}

    def __init__(self, schema_path: str, rules_path: str | None = None):
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)

        self.field_maps: dict[str, dict] = {}
        self.inference_rules: dict[str, dict] = {}
        if rules_path:
            self._load_rules(rules_path)

    def _load_rules(self, rules_path: str):
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

        for field_name, rule in rules.items():
            if field_name == "inference":
                self.inference_rules = rule
            elif isinstance(rule, dict) and "map" in rule:
                raw_map = rule["map"]
                self.field_maps[field_name] = {
                    str(k).strip().lower(): v for k, v in raw_map.items()
                }

    def clean(self, row_dict: dict) -> dict:
        result = {}
        for field in self.schema["fields"]:
            name = field["name"]
            raw = row_dict.get(name)

            if name in self.PASS_THROUGH_FIELDS:
                result[name] = raw
            elif name == "age":
                # Try map first, fall back to numeric parsing
                if name in self.field_maps:
                    mapped = self.field_maps[name].get(str(raw).strip().lower())
                else:
                    mapped = None
                result[name] = self._clean_age(mapped if mapped is not None else raw)
            elif name in self.field_maps:
                raw_str = str(raw).strip()
                mapped = self.field_maps[name].get(raw_str.lower())
                if mapped is not None:
                    # 映射表中有匹配，使用映射值
                    result[name] = mapped
                else:
                    # 映射表中没有匹配
                    std_vals = field.get("standard_values")
                    if std_vals is None:
                        # 字段没有预定义标准值列表，保留原值（只要不是空值）
                        result[name] = raw_str if raw_str else None
                    elif raw_str in std_vals:
                        # 原值本身就是标准值，保留原值
                        result[name] = raw_str
                    else:
                        # 既不在映射表中，也不是标准值，设为 None
                        result[name] = None
            else:
                result[name] = None
        return result

    def _clean_age(self, raw) -> int | None:
        """Extract integer age 0-120 from raw value or mapped candidate."""
        if raw is None:
            return None
        s = str(raw).strip()
        if s.isdigit():
            val = int(s)
            return val if 0 <= val <= 120 else None
        return None

    def is_important_field(self, field: str) -> bool:
        return field in self.IMPORTANT_FIELDS
