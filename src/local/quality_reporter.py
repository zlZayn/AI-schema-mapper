"""Quality reporter: completeness and compliance metrics."""

import json

import pandas as pd


class QualityReporter:
    def __init__(self, schema_path: str):
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)

    def generate(self, df: pd.DataFrame, report_path: str) -> dict:
        total = len(df)
        report = {"total_rows": total, "fields": {}}

        for field in self.schema["fields"]:
            name = field["name"]
            if name not in df.columns:
                continue
            non_null = df[name].notna() & (df[name] != "") & (df[name] != "null")
            completeness = round(non_null.sum() / total * 100, 2)

            field_report = {
                "completeness_pct": completeness,
                "non_null_count": int(non_null.sum()),
                "null_count": int(total - non_null.sum()),
            }

            if field.get("standard_values"):
                valid = df[name].isin(field["standard_values"])
                compliance = round(valid.sum() / total * 100, 2)
                field_report["compliance_pct"] = compliance

            report["fields"][name] = field_report

        overall = round(
            sum(f["completeness_pct"] for f in report["fields"].values())
            / len(report["fields"]),
            2,
        )
        report["overall_completeness_pct"] = overall

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report
