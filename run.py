"""Entry point: generate dirty data, run ETL pipeline, produce quality report."""

import os
import sys
import random
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import API_KEY, API_URL, MODEL
from src.etl_pipeline import ETLPipeline
from src.quality_reporter import QualityReporter
from src.rule_generator import RuleGenerator
from src.logger import section, step, ok, warn, start_timer, done


def generate_dirty_data(output_path: str, n: int = 150):
    random.seed(42)

    genders = [
        # 英文变体
        "M",
        "F",
        "Male",
        "Female",
        "MALE",
        "male",
        "female",
        "m",
        "f",
        "boy",
        "BOY",
        "girl",
        "GIRL",
        # 数字编码
        "1",
        "2",
        "0",
        "9",
        # 中文口语/尊称
        "先生",
        "女士",
        "帅哥",
        "美女",
        "大叔",
        "阿姨",
        # 拼音/缩写
        "N",
        "nv",
        "nan",
        "NB",
        "G",
        "B",
        # 极端脏数据
        "雌",
        "雄",
        "公",
        "母",
        "不详",
        "保密",
        "未填",
        "无",
        "nan",
        "N/A",
        "NULL",
        "null",
        "None",
        "none",
        "???",
        # 混入上下文
        "性别：男",
        "性别：女",
        "患者为男性",
        "该患者女",
        # 错别字
        "难",
        "蓝",
        "南",
        "兰",
        # 带空格/特殊字符
        " 男 ",
        " 女 ",
        "男 ",
        " 女",
        "M ",
        " F",
    ]

    depts = [
        # 复杂变体
        "心脏内科中心",
        "心内一区",
        "心内二科",
        "心血管内科门诊",
        "儿内科",
        "儿外科",
        "小儿呼吸科",
        "新生儿科病房",
        "儿科急诊",
        "妇产科病房",
        "妇科门诊",
        "产科一病区",
        "妇产",
        "妇科（计划生育）",
        "急诊科（抢救室）",
        "急诊内科",
        "急诊外科",
        "急诊ICU",
        "脑外科",
        "神经外科一区",
        "神经内科门诊",
        "脑病科",
        "骨科（创伤）",
        "骨伤科",
        "骨一科",
        "脊柱外科",
        "呼吸科",
        "呼吸与危重症医学科",
        "呼吸内科二区",
        "消化内科门诊",
        "消化血液内科",
        "脾胃病科",
        # 极端脏数据
        "内1科",
        "外2科",
        "综合科",
        "全科医疗",
        "ICU",
        "EICU",
        "SICU",
        "CCU",
        "中医科",
        "针灸推拿科",
        "康复医学中心",
        "眼科",
        "耳鼻喉科",
        "口腔颌面外科",
        "泌尿外科",
        "肾内科",
        "内分泌风湿免疫科",
        "肿瘤内科一区",
        "放疗科",
        "血液透析中心",
        # 拼音/英文混入
        "Neurology",
        "Cardiology",
        "ER",
        "OR",
        # 极端模糊
        "内科（具体不详）",
        "外科？",
        "未分科",
        "门诊",
        "住院部",
    ]

    drugs = [
        # 带剂型/规格
        "阿莫西林克拉维酸钾分散片",
        "阿莫西林胶囊0.25g",
        "阿莫西林颗粒",
        "布洛芬缓释胶囊(芬必得)",
        "布洛芬混悬液(美林)",
        "布洛芬片0.2g",
        "对乙酰氨基酚片(泰诺林)",
        "泰诺（对乙酰氨基酚）",
        "扑热息痛",
        "头孢克洛缓释片",
        "头孢地尼胶囊",
        "头孢呋辛酯片",
        "甲硝唑片0.2g",
        "甲硝唑氯化钠注射液",
        "阿奇霉素片(希舒美)",
        "阿奇霉素干混悬剂",
        "硝苯地平控释片(拜新同)",
        "氨氯地平片(络活喜)",
        "二甲双胍缓释片(格华止)",
        "格列美脲片",
        "奥美拉唑肠溶胶囊",
        "兰索拉唑片",
        # 缩写/代码
        "AMXL",
        "AMX",
        "IBU",
        "APAP",
        "CTX",
        "AZM",
        "NFP",
        "AML",
        "MET",
        "OME",
        "LAN",
        # 极端脏数据
        "阿莫胶囊",
        "阿莫西林？",
        "布洛芬？",
        "头孢类",
        "抗生素（具体不详）",
        "降压药",
        "止痛药",
        "胃药",
        "消炎药",
        "unknown",
        "不详",
        "忘记带了",
        "患者自述不详",
        "NULL",
        "null",
        "/",
        "-",
        "无",
        "未用药",
        # 混入剂量信息
        "阿莫西林 2粒 tid",
        "布洛芬 prn",
        "头孢 1支 qd",
    ]

    diags = [
        # 标准ICD-10
        "I10",
        "I10.0",
        "I10.01",
        "I10.9",
        "J45.9",
        "J45.909",
        "J45.0",
        "J18.9",
        "E11.9",
        "E11.65",
        "E10.9",
        "E11.0",
        "K21.0",
        "K35.9",
        "K80.1",
        "N39.0",
        "N18.9",
        "N40",
        "M54.5",
        "M79.3",
        "M17.1",
        "S72.0",
        "S42.2",
        "T14.1",
        # 中文诊断名
        "高血压",
        "高血压病",
        "高血压病3级",
        "原发性高血压",
        "2型糖尿病",
        "糖尿病",
        "糖尿病酮症酸中毒",
        "冠心病",
        "急性心肌梗死",
        "心房颤动",
        "肺炎",
        "支气管哮喘",
        "慢性阻塞性肺疾病",
        "急性阑尾炎",
        "胆囊结石",
        "胃溃疡",
        "脑梗塞",
        "脑出血",
        "短暂性脑缺血发作",
        # 极端脏数据
        "高血压？",
        "疑似糖尿病",
        "待查",
        "I10（高血压）",
        "E11-糖尿病",
        "J45/哮喘",
        "htn",
        "DM",
        "COPD",
        "CHD",
        "AF",
        "NULL",
        "null",
        "None",
        "none",
        "N/A",
        "无",
        "",
        " ",
        "未确诊",
        "体检",
        "复查",
        # 格式错误
        " I10 ",
        "I10.01.1",
        "I-10",
        "i10",
        "E11。9",
        "J45，909",
        "E11.900",
    ]

    ages = [
        # 中文数字
        "三十岁",
        "三十五岁",
        "四十岁",
        "四十五岁",
        "五十岁",
        "五十五岁",
        "六十岁",
        "六十五岁",
        "七十岁",
        "七十五岁",
        "八十岁",
        "八十八岁",
        "二十岁",
        "二十五岁",
        "二十八岁",
        "十八岁",
        "十六岁",
        "十五岁",
        # 带单位变体
        "30岁",
        "35岁",
        "40岁",
        "50岁",
        "60岁",
        "30",
        "35",
        "40",
        "50",
        "60",
        "5个月",
        "3个月",
        "1岁半",
        "2岁3个月",
        "约30岁",
        "大概40",
        "50左右",
        "30多岁",
        # 极端脏数据
        "未知",
        "不详",
        "未填",
        "忘记了",
        "不清楚",
        "大于100",
        "超过90",
        "不到20",
        "100+",
        "<5",
        "-3",
        "-1",
        "200",
        "300",
        "999",
        "三十",
        "四十",
        "五十",
        "六十",
        "三十五",
        "四十八",
        "六十七",
        "八十二",
        # 嵌入文本
        "患者年龄约35岁",
        "年龄：40",
        "男，35岁",
        "nan",
        "NULL",
        "null",
        "None",
        "/",
        "-",
        "",
        "2天",
        "3周",
        "6个月",
        "10个月",
    ]

    # 预定义跨字段推断行：gender缺失，但科室暗示性别（体现Agent语义推断能力）
    inference_rows = [
        # 妇科/产科 + gender缺失 → Agent推断为"女"
        {
            "gender": "",
            "age": "35岁",
            "dept_name": "妇科门诊",
            "drug_name": "甲硝唑片",
            "diagnosis_code": "N80.0",
        },
        {
            "gender": "NULL",
            "age": "28",
            "dept_name": "妇产科",
            "drug_name": "AMXL",
            "diagnosis_code": "N97.0",
        },
        {
            "gender": "nan",
            "age": "四十岁",
            "dept_name": "妇科（计划生育）",
            "drug_name": "头孢地尼",
            "diagnosis_code": "N73.0",
        },
        {
            "gender": "未知",
            "age": "三十岁",
            "dept_name": "产科",
            "drug_name": "阿莫西林",
            "diagnosis_code": "O24.4",
        },
        {
            "gender": "未填",
            "age": "二十五岁",
            "dept_name": "产科一病区",
            "drug_name": "头孢呋辛酯片",
            "diagnosis_code": "O80",
        },
        # 儿科 + age缺失（Agent无法推断年龄，但能正确映射科室）
        {
            "gender": "男",
            "age": "",
            "dept_name": "儿内科",
            "drug_name": "布洛芬混悬液",
            "diagnosis_code": "J45.909",
        },
        {
            "gender": "F",
            "age": "不详",
            "dept_name": "小儿呼吸科",
            "drug_name": "AMX",
            "diagnosis_code": "J18.9",
        },
        # 多字段缺失 + 剂型/缩写 → 体现Agent同时处理多种脏数据
        {
            "gender": "",
            "age": "未知",
            "dept_name": "妇产科病房",
            "drug_name": "阿莫西林克拉维酸钾分散片",
            "diagnosis_code": "",
        },
        {
            "gender": "???",
            "age": "",
            "dept_name": "妇科门诊",
            "drug_name": "APAP",
            "diagnosis_code": "子宫肌瘤",
        },
        {
            "gender": "保密",
            "age": "100+",
            "dept_name": "产科",
            "drug_name": "头孢类",
            "diagnosis_code": "O80.9",
        },
    ]

    rows = []
    for i in range(n):
        if i < len(inference_rows):
            r = inference_rows[i]
        else:
            r = {
                "gender": random.choice(genders),
                "age": random.choice(ages),
                "dept_name": random.choice(depts),
                "drug_name": random.choice(drugs),
                "diagnosis_code": random.choice(diags),
            }
        row = {
            "patient_id": f"P{random.randint(100, 999)}",
            **r,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    step(f"生成 {n} 行 -> {output_path}")


def main():
    data_dir = os.path.join(BASE_DIR, "data")
    output_dir = os.path.join(BASE_DIR, "output")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    dirty_path = os.path.join(data_dir, "super_dirty_data.csv")
    schema_path = os.path.join(data_dir, "standard_schema.json")
    cleaned_path = os.path.join(output_dir, "final_cleaned.csv")
    report_path = os.path.join(output_dir, "quality_report.json")
    rules_path = os.path.join(data_dir, "auto_rules.json")

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
        generator = RuleGenerator(API_KEY, API_URL, MODEL)
        generator.run(dirty_path, rules_path, schema_path)

    # Step 3
    section("[3/4]  执行 ETL 清洗")
    pipeline = ETLPipeline(
        schema_path,
        API_KEY,
        skip_agent=no_api_key,
        rules_path=rules_path,
        api_url=API_URL,
        model=MODEL,
        max_workers=10,
        verbose=False,
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
    done()


if __name__ == "__main__":
    main()
