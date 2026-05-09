"""Main pipeline orchestrator for Schema Mapper."""

import json

import pandas as pd
from src.local.rule_mapper import RuleCleaner
from src.llm.rule_refiner import LLMRuleRefiner
from src.local.final_polisher import FinalPolisher
from src.local.logger import step, ok, warn


class ETLPipeline:
    def __init__(
        self,
        schema_path: str,
        api_key: str,
        skip_llm_refinement: bool = False,
        rules_path: str | None = None,
        base_url: str = None,
        model: str = None,
        verbose: bool = False,
        cache_path: str = None,
    ):
        self.schema_path = schema_path
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)

        self.rule_cleaner = RuleCleaner(schema_path, rules_path)
        self.skip_llm_refinement = skip_llm_refinement
        self.verbose = verbose

        if not skip_llm_refinement:
            kwargs = {"base_url": base_url, "model": model, "verbose": verbose, "cache_path": cache_path}
            self.rule_refiner = LLMRuleRefiner(
                schema_path,
                api_key,
                **{k: v for k, v in kwargs.items() if v is not None},
            )

    def run(self, input_path: str, output_path: str) -> pd.DataFrame:
        df = pd.read_csv(input_path)
        total = len(df)

        # Phase 1 — first pass: rule-based cleaning (fast, sequential)
        step(f"第一轮规则清洗 ({total} 行)...")
        rule_results = []
        for _, row in df.iterrows():
            rule_results.append(self.rule_cleaner.clean(row.to_dict()))
        ok("第一轮规则清洗完成")

        # Phase 1.5 — cross-field inference from cleaned data (no API calls)
        rule_results = self._infer_cross_field(rule_results)

        # Phase 2 — second pass: AI refines remaining issues (1 API call)
        if not self.skip_llm_refinement:
            # Extract remaining problematic values
            temp_df = pd.DataFrame(rule_results)
            remaining_values = LLMRuleRefiner.extract_remaining_values(
                temp_df, self.schema
            )

            if remaining_values:
                step(f"发现残余问题值，生成整理规则...")
                # Generate refinement rules (1 LLM call)
                refinement_rules = self.rule_refiner.generate_refinement_rules(
                    remaining_values, "data/refinement_rules.json"
                )

                # Apply refinement rules locally
                if refinement_rules:
                    step("应用整理规则...")
                    rule_results = self._apply_refinement_rules(
                        rule_results, refinement_rules
                    )
                    ok("第二轮规则清洗完成")
            else:
                ok("无残余问题，跳过整理")

        final_df = pd.DataFrame(rule_results)

        # Phase 3 — validate output against schema
        violations = self._validate_schema(final_df)
        if violations:
            warn(f"Schema 违规: {len(violations)} 处 (见上方)")

        # Phase 4 — final polish (local, zero API calls)
        polisher = FinalPolisher(self.schema_path)
        final_df = polisher.polish_dataframe(final_df)

        final_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        ok(f"清洗结果 -> {output_path}")
        return final_df

    def _apply_refinement_rules(self, rows: list[dict], rules: dict) -> list[dict]:
        """Apply AI-generated refinement rules locally."""
        missing_values = rules.get("missing_values", {})
        uncertain_values = rules.get("uncertain_values", {})
        type_fixes = rules.get("type_fixes", {})

        for row in rows:
            for field_name, value in row.items():
                if value is None:
                    continue

                str_val = str(value).strip()

                # Apply missing_values mapping
                if field_name in missing_values:
                    if str_val in missing_values[field_name]:
                        row[field_name] = None
                        continue

                # Apply uncertain_values mapping
                if field_name in uncertain_values:
                    if str_val in uncertain_values[field_name]:
                        row[field_name] = uncertain_values[field_name][str_val]
                        continue

                # Apply type_fixes
                if field_name in type_fixes:
                    fixes = type_fixes[field_name]
                    if fixes.get("trim_whitespace") and isinstance(value, str):
                        value = value.strip()
                    if fixes.get("remove_decimals"):
                        try:
                            value = int(float(value))
                        except (ValueError, TypeError):
                            pass
                    row[field_name] = value

        return rows

    def _infer_cross_field(self, rows: list[dict]) -> list[dict]:
        """Apply AI-generated cross-field inference rules from auto_rules.json."""
        infer = self.rule_cleaner.inference_rules
        if not infer:
            return rows

        cnt = 0
        applied_rules = set()
        uncertain_values = {"未知", "不详", "未填", "不确定", "待查", "保密"}

        for source_field, rules in infer.items():
            for source_val, targets in rules.items():
                cleaned_source_val = self._clean_value_for_inference(
                    source_field, source_val
                )

                for target_field, inferred in targets.items():
                    rule_key = (
                        source_field,
                        cleaned_source_val,
                        target_field,
                        inferred,
                    )
                    rule_applied = False

                    for row in rows:
                        current_val = row.get(target_field)
                        should_apply = row.get(source_field) == cleaned_source_val and (
                            current_val is None
                            or current_val == ""
                            or str(current_val) in uncertain_values
                        )
                        if should_apply:
                            row[target_field] = inferred
                            cnt += 1
                            rule_applied = True

                    if rule_applied and rule_key not in applied_rules:
                        step(
                            f"推理: {source_field}='{cleaned_source_val}' -> {target_field}='{inferred}'"
                        )
                        applied_rules.add(rule_key)

        if cnt:
            ok(f"应用 {cnt} 条 AI 推理规则")

        return rows

    def _clean_value_for_inference(self, field_name: str, value: str) -> str:
        """Clean a value using field maps for inference matching."""
        if field_name in self.rule_cleaner.field_maps:
            cleaned = self.rule_cleaner.field_maps[field_name].get(
                str(value).strip().lower()
            )
            if cleaned is not None:
                return cleaned
        return value

    def _validate_schema(self, df: pd.DataFrame) -> list[dict]:
        """Run basic schema validation and print warnings for violations."""
        violations = []
        for field in self.schema["fields"]:
            name, dtype = field["name"], field.get("type", "string")
            if name not in df.columns:
                continue
            col = df[name]

            for idx, val in col.items():
                if pd.isna(val) or val in ("", "null", "None"):
                    continue

                if dtype == "integer" and "min" in field and "max" in field:
                    try:
                        ival = int(val)
                        if not (field["min"] <= ival <= field["max"]):
                            warn(
                                f"Row {idx}: {name}={val} out of range [{field['min']}, {field['max']}]"
                            )
                            violations.append(
                                {
                                    "row": idx,
                                    "field": name,
                                    "value": val,
                                    "reason": "out_of_range",
                                }
                            )
                    except (ValueError, TypeError):
                        warn(f"Row {idx}: {name}={val} is not a valid integer")
                        violations.append(
                            {
                                "row": idx,
                                "field": name,
                                "value": val,
                                "reason": "not_integer",
                            }
                        )

                if dtype == "string" and field.get("standard_values"):
                    if str(val) not in field["standard_values"]:
                        warn(
                            f"Row {idx}: {name}='{val}' not in {field['standard_values']}"
                        )
                        violations.append(
                            {
                                "row": idx,
                                "field": name,
                                "value": val,
                                "reason": "not_standard",
                            }
                        )
        return violations
