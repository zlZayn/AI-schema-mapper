"""Main ETL pipeline orchestrator."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from src.rule_cleaner import RuleCleaner
from src.llm_cleaner import LLMCleaner
from src.logger import step, ok, warn


class ETLPipeline:
    def __init__(
        self,
        schema_path: str,
        api_key: str,
        skip_agent: bool = False,
        rules_path: str | None = None,
        api_url: str = None,
        model: str = None,
        max_workers: int = 4,
        verbose: bool = False,
    ):
        self.schema_path = schema_path
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)

        self.rule_cleaner = RuleCleaner(schema_path, rules_path)
        self.skip_agent = skip_agent
        self.max_workers = max_workers
        self.verbose = verbose

        if not skip_agent:
            kwargs = {"api_url": api_url, "model": model, "verbose": verbose}
            self.llm_cleaner = LLMCleaner(
                schema_path,
                api_key,
                **{k: v for k, v in kwargs.items() if v is not None},
            )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, input_path: str, output_path: str) -> pd.DataFrame:
        df = pd.read_csv(input_path)
        total = len(df)

        # Phase 1 — rule-based cleaning (fast, sequential)
        step(f"规则清洗 ({total} 行)...")
        rule_results = []
        for _, row in df.iterrows():
            rule_results.append(self.rule_cleaner.clean(row.to_dict()))
        ok("规则清洗完成")

        # Phase 1.5 — cross-field inference from cleaned data (no API calls)
        rule_results = self._infer_cross_field(rule_results)

        # Phase 2 — agent cleaning for rows that still need it (slow, parallel)
        agent_call_count = 0
        if not self.skip_agent:
            needs_agent = [
                (i, df.iloc[i].to_dict())
                for i, r in enumerate(rule_results)
                if self._needs_agent(r)
            ]
            agent_call_count = len(needs_agent)
            if needs_agent:
                step(
                    f"Agent 清洗 ({agent_call_count}/{total} 行, {self.max_workers} 并发)..."
                )
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_idx = {
                        executor.submit(self.llm_cleaner.clean, row_dict): idx
                        for idx, row_dict in needs_agent
                    }
                    done_cnt = 0
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        agent_result = future.result()
                        if agent_result:
                            for key in rule_results[idx]:
                                agent_val = agent_result.get(key)
                                if agent_val is None:
                                    continue
                                cur_val = rule_results[idx][key]
                                if cur_val is None:
                                    rule_results[idx][key] = agent_val
                                elif self._is_non_compliant(rule_results[idx], key):
                                    rule_results[idx][key] = agent_val
                        done_cnt += 1
                    ok(f"Agent 清洗完成 (调用 {agent_call_count} 次)")
            else:
                ok("无需 Agent 清洗")

        final_df = pd.DataFrame(rule_results)

        # Phase 3 — validate output against schema
        violations = self._validate_schema(final_df)
        if violations:
            warn(f"Schema 违规: {len(violations)} 处 (见上方)")

        final_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        ok(f"清洗结果 -> {output_path}")
        return final_df

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer_cross_field(self, rows: list[dict]) -> list[dict]:
        """Apply AI-generated cross-field inference rules from auto_rules.json."""
        infer = self.rule_cleaner.inference_rules
        if not infer:
            return rows

        cnt = 0
        for source_field, rules in infer.items():
            for source_val, targets in rules.items():
                for target_field, inferred in targets.items():
                    for row in rows:
                        if (
                            row.get(source_field) == source_val
                            and row.get(target_field) is None
                        ):
                            row[target_field] = inferred
                            cnt += 1
                    if cnt:
                        step(
                            f"推理: {source_field}='{source_val}' -> {target_field}='{inferred}'"
                        )

        if cnt:
            ok(f"应用 {cnt} 条 AI 推理规则")

        return rows

    def _needs_agent(self, row: dict) -> bool:
        """A row needs agent if any important field is null or non-compliant."""
        check_fields = [f["name"] for f in self.schema["fields"]]
        return any(
            self._is_non_compliant(row, name)
            for name in check_fields
            if self.rule_cleaner.is_important_field(name)
        )

    def _is_non_compliant(self, row: dict, field_name: str) -> bool:
        val = row.get(field_name)
        if val is None:
            return True

        # Find schema definition for this field
        field_def = None
        for f in self.schema["fields"]:
            if f["name"] == field_name:
                field_def = f
                break
        if not field_def:
            return False

        dtype = field_def.get("type", "string")

        # Type compliance: age must be integer
        if dtype == "integer":
            try:
                iv = int(val)
                if float(iv) != float(val):
                    return True  # e.g. 0.5 → not integer
            except (ValueError, TypeError):
                return True

        # Type compliance for string fields — reject non-string values
        if dtype == "string" and not isinstance(val, str):
            return True

        # Standard values compliance
        sv = field_def.get("standard_values")
        if sv and str(val) not in sv:
            return True

        # Range compliance
        if dtype == "integer" and "min" in field_def and "max" in field_def:
            try:
                iv = int(val)
                if not (field_def["min"] <= iv <= field_def["max"]):
                    return True
            except (ValueError, TypeError):
                return True

        return False

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
                # Type check
                if dtype == "integer":
                    try:
                        int(val)
                    except (ValueError, TypeError):
                        pass  # non-integer will be caught by min/max, skip type-only warning for clarity

                # Range check for integer
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

                # Standard values check for string
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
