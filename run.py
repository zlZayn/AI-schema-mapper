"""
SignalChain Data Cleaning Tool

自动生成脏数据 → 自动生成清洗规则 → 脚本清洗 → 输出质量报告

固定文件路径：
    脏数据: data/super_dirty_data.csv
    输出: output/final_cleaned.csv
    报告: output/quality_report.json

用法:
    python run.py           # 执行全流程（使用缓存）
    python run.py --no-cache # 强制重新调用 LLM，不使用缓存
"""

import os
import sys
import argparse
from config import API_KEY, API_BASE_URL, MODEL
from src.etl_pipeline import ETLPipeline
from src.local.quality_reporter import QualityReporter
from src.llm.rule_generator import RuleGenerator
from src.local.logger import section, step, ok, warn, start_timer, done
from src.cost_tracker import reset as cost_reset, summary as cost_summary
from src.data_generator import generate_dirty_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def main():
    cost_reset()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-cache", action="store_true", help="跳过缓存，强制调用 LLM"
    )
    args = parser.parse_args()

    data_dir = os.path.join(BASE_DIR, "data")
    output_dir = os.path.join(BASE_DIR, "output")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    dirty_path = os.path.join(data_dir, "super_dirty_data.csv")
    schema_path = os.path.join(data_dir, "standard_schema.json")
    cleaned_path = os.path.join(output_dir, "final_cleaned.csv")
    report_path = os.path.join(output_dir, "quality_report.json")
    rules_path = os.path.join(data_dir, "auto_rules.json")
    cache_path = os.path.join(data_dir, ".rule_cache.json")
    if args.no_cache and os.path.exists(cache_path):
        os.remove(cache_path)
        step("已清除缓存")

    no_api_key = API_KEY == "sk-your-deepseek-api-key-here"
    start_timer()

    # Step 1
    section("[1/4]  生成脏数据")
    generate_dirty_data(dirty_path)

    # Step 2
    section("[2/4]  自动生成规则 (AI 扫描)")
    if no_api_key:
        warn("未配置 API Key，跳过规则生成", "编辑 config.py 设置 Key")
        rules_path = None
    else:
        generator = RuleGenerator(API_KEY, API_BASE_URL, MODEL)
        generator.run(dirty_path, rules_path, schema_path, cache_path)

    # Step 3
    section("[3/4]  执行 ETL 清洗")
    pipeline = ETLPipeline(
        schema_path,
        API_KEY,
        skip_llm_refinement=no_api_key,
        rules_path=rules_path,
        base_url=API_BASE_URL,
        model=MODEL,
        verbose=False,
        cache_path=cache_path,
    )
    cleaned_df = pipeline.run(dirty_path, cleaned_path)

    # Step 4
    section("[4/4]  生成质量报告")
    reporter = QualityReporter(schema_path)
    report = reporter.generate(cleaned_df, report_path)
    ok(f"整体完整度: {report['overall_completeness_pct']}%")

    step("各字段详情:")
    for name, info in report["fields"].items():
        parts = [f"完整度={info['completeness_pct']}%"]
        if "compliance_pct" in info:
            parts.append(f"合规率={info['compliance_pct']}%")
        ok(f"{name}: {', '.join(parts)}")

    ok(f"清洗结果 -> {cleaned_path}")
    ok(f"质量报告 -> {report_path}")

    section("API 费用汇总")
    print(cost_summary())

    done()


if __name__ == "__main__":
    main()
