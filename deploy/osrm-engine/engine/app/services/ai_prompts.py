"""
AI 分析提示词模板
=================

所有 AI 分析任务的 System Prompt 和 User Prompt 模板集中在此。
每个模板是返回 (system_prompt, user_prompt_builder) 的函数。
"""

import json


# ══════════════════════════════════════════════════════════════
# 1. 价格偏差分析
# ══════════════════════════════════════════════════════════════

PRICE_DEVIATION_SYSTEM = """你是一位越南物流成本分析专家，精通公路运输定价模型。

你的任务：分析 OSRM++ 运费公式的计算结果与供应商真实报价之间的偏差，
找出系统性误差的根因，并给出可操作的优化建议。

分析维度：
1. 距离相关偏差 —— 公式对短途/长途是否存在系统性高估或低估？
2. 车型相关偏差 —— 哪些车型的误差特别大？是 base_rate 还是 fixed_surcharge 不准？
3. 路线特征偏差 —— 港口、山区、边境路线是否存在特殊溢价未被公式捕获？
4. 异常值 —— 哪些个别样本的误差远超正常范围？可能的原因是什么？

输出严格要求 JSON 格式。"""


def build_price_deviation_prompt(
    predictions: list[dict],
    vehicle_models: dict[str, dict],
    context: str = "",
) -> str:
    return f"""请分析以下 {len(predictions)} 条运费预测偏差：

{context}

## 车型参数
{json.dumps(vehicle_models, ensure_ascii=False, indent=2)}

## 预测偏差数据
{json.dumps(predictions, ensure_ascii=False, indent=2)}

请按 JSON 格式输出分析结果：
{{
  "summary": "一句话总结核心发现",
  "overall_stats": {{
    "mean_abs_error_pct": 数字,
    "median_abs_error_pct": 数字,
    "max_error_pct": 数字,
    "samples_within_10pct": 数字,
    "samples_within_20pct": 数字
  }},
  "distance_pattern": {{
    "short_haul_bias": "under/over/none — 短途(<200km)的系统性偏差方向",
    "long_haul_bias": "under/over/none — 长途(>400km)的系统性偏差方向",
    "explanation": "解释原因"
  }},
  "vehicle_issues": [
    {{
      "model_id": "车型ID",
      "issue": "问题描述",
      "evidence": "数据支撑",
      "suggestion": "具体优化建议"
    }}
  ],
  "route_feature_gaps": [
    {{
      "feature": "未被捕获的路线特征(如港口/山区/边境)",
      "evidence": "数据支撑",
      "estimated_premium_vnd": 估计溢价金额
    }}
  ],
  "anomalies": [
    {{
      "sample": "异常样本描述",
      "error_pct": 偏差百分比,
      "likely_cause": "可能原因"
    }}
  ],
  "top_recommendations": ["优先级最高的3-5条优化建议"]
}}"""


# ══════════════════════════════════════════════════════════════
# 2. 路线特征识别
# ══════════════════════════════════════════════════════════════

ROUTE_FEATURE_SYSTEM = """你是一位越南地理与物流专家。你的任务是根据目的地地址判断路线特征。

越南物流中，以下路线特征会影响运费：
- port（港口）：海防市、广宁省、头顿、岘港、胡志明市港口区
- border（边境口岸）：Huu Nghi(友谊关)、Tan Thanh、Chi Ma、Mong Cai(芒街)、Lao Cai(老街)
- mountain（山区）：北部山区(Lai Chau, Dien Bien, Son La, Ha Giang, Cao Bang)、西原地区
- industrial_park（工业区）：Bac Ninh, Bac Giang, Thai Nguyen, Vinh Phuc, Hai Duong, Hung Yen
- city_center（市中心）：Ha Noi trung tam, TP HCM trung tam

输出严格要求 JSON 格式。"""


def build_route_feature_prompt(destinations: list[str]) -> str:
    return f"""请分析以下 {len(destinations)} 个越南目的地的路线特征：

{json.dumps(destinations, ensure_ascii=False)}

对每个目的地输出：
{{
  "results": [
    {{
      "dest": "目的地名称",
      "features": {{
        "is_port": true/false,
        "is_border": true/false,
        "is_mountain": true/false,
        "is_industrial_park": true/false,
        "is_city_center": true/false,
        "province": "省份名",
        "estimated_premium_category": "normal/port/border/mountain"
      }},
      "confidence": "high/medium/low",
      "notes": "简短说明"
    }}
  ]
}}"""


# ══════════════════════════════════════════════════════════════
# 3. 供应商报价智能提取
# ══════════════════════════════════════════════════════════════

QUOTE_EXTRACTION_SYSTEM = """你是越南供应商报价单的专业数据提取助手。

你收到的是一份报价单的文本内容（可能是从 Excel/PDF/图片 OCR 得到的），
请从中提取所有报价数据行，规范化后输出为标准 JSON 格式。

提取规则：
1. 起点(origin)：报价单抬头有公司地址则提取，否则从上下文推断
2. 终点(dest)：矩阵中每一行的目的地列
3. 车型(vehicle_type)：矩阵中每一列的列名，直接复制原文（不要翻译）
4. 价格(price_vnd)：矩阵单元格中的数字，统一转为整数 VND
5. 页脚说明写进每条样本的 notes

越南语数字格式注意：
- "1.600.000" = 1600000（点是千分位）
- "3tr2" = 3200000
- "500k" = 500000

输出严格要求 JSON 格式。"""


def build_quote_extraction_prompt(raw_text: str) -> str:
    if len(raw_text) > 30000:
        raw_text = raw_text[:30000] + "\n... (内容已截断)"

    return f"""请从以下报价单文本中提取所有报价数据：

```
{raw_text}
```

请输出：
{{
  "supplier_name": "报价方公司名",
  "supplier_address": "报价方地址",
  "quote_date": "报价日期(如有)",
  "loading_mode": "full_truck/consolidated/unknown",
  "notes": "脚注/备注文字原文",
  "samples": [
    {{
      "dest": "目的地",
      "vehicle_type": "车型（原文列名）",
      "price_vnd": 数字,
      "notes": "该行特殊说明"
    }}
  ],
  "extraction_confidence": "high/medium/low",
  "warnings": ["提取中的不确定项"]
}}"""


# ══════════════════════════════════════════════════════════════
# 4. 公式优化建议
# ══════════════════════════════════════════════════════════════

FORMULA_OPTIMIZATION_SYSTEM = """你是物流定价模型的优化顾问。

OSRM++ 的运费公式是：
  总价 = 距离 x base_rate x 货物系数 x 返空系数 + fixed_surcharge + 路桥费 + 装卸费 + 保险费 + 路况附加

其中：
- base_rate_vnd_per_km 和 fixed_surcharge_vnd 是每个车型的可调参数
- 路况附加包括：禁限行绕行、施工封闭、上坡山区、港口目的地

根据提供的预测偏差数据，给出具体的参数调整建议。
只建议有数据支撑的调整，不确定的明确标注。

输出严格要求 JSON 格式。"""


def build_formula_optimization_prompt(
    current_params: dict,
    error_analysis: dict,
) -> str:
    return f"""## 当前公式参数
{json.dumps(current_params, ensure_ascii=False, indent=2)}

## 误差分析结果
{json.dumps(error_analysis, ensure_ascii=False, indent=2)}

请输出：
{{
  "parameter_adjustments": [
    {{
      "model_id": "车型ID",
      "param": "base_rate_vnd_per_km 或 fixed_surcharge_vnd",
      "current_value": 当前值,
      "suggested_value": 建议值,
      "rationale": "调整理由和数据支撑",
      "confidence": "high/medium/low",
      "expected_impact": "预期误差改善描述"
    }}
  ],
  "structural_changes": [
    {{
      "change": "结构性改动建议",
      "rationale": "理由",
      "priority": "high/medium/low"
    }}
  ],
  "no_change_items": [
    {{
      "param": "不需要调整的参数",
      "reason": "为什么不需要调整"
    }}
  ],
  "summary": "优化总结"
}}"""
