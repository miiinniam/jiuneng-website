"""v006 能力注册表 · 能力声明（**唯一真源**）。

⚠️ 本文件是「AI 能做什么」的唯一声明处，以下全部**由它生成**：
- LLM 的 tool schema（`app/ai/registry.tool_schemas()`）
- 系统提示里的工具清单（`app/ai/registry.tools_prompt_block()`）
- 权限 / 确认 / 审计元数据（kind / confirm / roles）

不要再去 `ai_tools.py` 或 `ai_chat_prompt.py` 里手写第二份 ——
v005 之前的老坑就是「加一个工具要同步改三处，必漏一处」。

`description` / `parameters` 由 `scripts/_v006_gen_spec.py` 从重构前的 TOOLS 原样搬运，
`prompt_line` 是 v005 系统提示里那一行的原文，等价性由
`backend/tests/test_capabilities.py` 的回归用例兜底。

字段：
- `kind`        read=只读查询 · write=会改状态 · destructive=不可逆
- `confirm`     True=执行前需用户确认（v006 第 3 步接 UI；当前仅声明）
- `roles`       允许调用的角色（`registry.ROLE_ENFORCEMENT` 打开后生效）
- `prompt_rank` 系统提示清单里的排序（保持与旧提示一致）
- `prompt_line` 系统提示清单里那一行的正文（由 registry 拼成 "N. **name** — {prompt_line}"）
- `locality`    backend=后端执行；frontend=下发到界面执行（v006 第 2 步）
- `prompt_hint` 触发条件（供后续场景段落生成 / 文档）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    description: str
    parameters: dict[str, Any]
    kind: str = "read"                                  # read | write | destructive
    confirm: bool = False                               # 执行前需用户确认
    roles: tuple[str, ...] = ("internal", "customer")   # 允许角色
    prompt_rank: int = 99                               # 提示词清单排序
    prompt_line: str = ""                               # 提示词清单行正文
    locality: str = "backend"                           # backend | frontend
    prompt_hint: str = ""                               # 触发条件


SPECS: list[CapabilitySpec] = [
    CapabilitySpec(
        name='calculate_freight_cost',
        description='计算越南境内公路运输费用。传入起点/终点地址（或经纬度）、货物重量和类型、车型等参数，返回真实计算结果（经过 OSRM 路线引擎和费用公式引擎），包含详细费用明细。\n\n重要：你必须调用这个工具来获取运费，绝不能凭空编造或凭记忆估计数字。',
        parameters={'type': 'object',
 'properties': {'origin': {'type': 'string',
                           'description': "起点地址或经纬度。越南地址用越南语，中国地址用中文。例如：'友谊关(Huu Nghi), Lạng "
                                          "Sơn' 或 '21.98,106.71'"},
                'destination': {'type': 'string',
                                'description': "终点地址或经纬度。例如：'Hà Nội, Hoàn Kiếm'"},
                'cargo_weight_ton': {'type': 'number', 'description': '货物重量（吨），如 25 表示 25 吨'},
                'cargo_type': {'type': 'string',
                               'enum': ['normal',
                                        'oversized',
                                        'heavy_equipment',
                                        'cold_chain',
                                        'hazardous',
                                        'other'],
                               'description': '货物类型，默认 normal（普通货）'},
                'vehicle_model_id': {'type': 'string',
                                     'description': '车型 ID，如 flatbed_13m, flatbed_17m5, '
                                                    'container_40ft '
                                                    '等。如果不指定，系统自动匹配最佳车型（整车模式必须指定车型或先查询车型列表）。'},
                'loading_mode': {'type': 'string',
                                 'enum': ['full_truck', 'consolidated'],
                                 'description': '运输模式：full_truck（整车）/ consolidated（拼货）。默认 '
                                                'full_truck。'},
                'empty_return': {'type': 'boolean',
                                 'description': '是否预估空返费用（加收空返附加费），默认 false'},
                'need_loading': {'type': 'boolean', 'description': '是否需要装卸费，默认 false'},
                'volume_m3': {'type': 'number',
                              'description': '货物体积（立方米）。拼货模式（consolidated）时必须提供。'},
                'items': {'type': 'array',
                          'description': '🆕 单件货物明细（可选）。用于精确判断车辆数（长件/不可堆叠货物）。格式: [{"name": '
                                         '"变压器", "count": 1, "length_m": 8, "width_m": 2.5, '
                                         '"height_m": 3.2, "weight_kg": 18000, "stackable": '
                                         'false}]。单件长度超过车厢地板长的货物、或不可堆叠设备必须提供此字段。',
                          'items': {'type': 'object',
                                    'properties': {'name': {'type': 'string'},
                                                   'count': {'type': 'integer', 'minimum': 1},
                                                   'length_m': {'type': 'number'},
                                                   'width_m': {'type': 'number'},
                                                   'height_m': {'type': 'number'},
                                                   'weight_kg': {'type': 'number'},
                                                   'stackable': {'type': 'boolean',
                                                                 'description': '是否可堆叠，默认 '
                                                                                'true'}},
                                    'required': ['length_m', 'width_m']}}},
 'required': ['origin', 'destination', 'cargo_weight_ton']},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=2,
        prompt_line='计算越南境内运输费（核心算价工具）',
        prompt_hint='用户问「X地到Y地运费多少」且不涉及建任务卡时调用（场景 B）',
    ),
    CapabilitySpec(
        name='calculate_border_fees',
        description="计算中国→越南进出口口岸操作费用（两端分开）。\n返回中国端费用（出口报关、货场、卸货、换车）和越南端费用（进口清关、货场）。\n不含关税/增值税，仅口岸操作费。\n\n参数只需车辆数，系统自动从玖能报价数据库读取各项固定费用。\n用户问'DDP''到门价''进出口费用''口岸费'时调用此工具。",
        parameters={'type': 'object',
 'properties': {'vehicle_count': {'type': 'integer',
                                  'description': '车辆数量（默认1）。如果运费计算返回多辆车，传入对应车数。'}},
 'required': []},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=3,
        prompt_line='计算口岸操作费（两端分开，不含税）',
        prompt_hint='用户问进出口/口岸费用、报关费、吊装费时调用（不是关税）',
    ),
    CapabilitySpec(
        name='query_vehicle_models',
        description='查询可用的运输车型及其参数（载重、尺寸、费率等）。帮用户选车时调用此工具，了解有哪些车型可选。',
        parameters={'type': 'object',
 'properties': {'category': {'type': 'string',
                             'enum': ['small_box',
                                      'flatbed',
                                      'high_side',
                                      'container',
                                      'cold_chain'],
                             'description': '车型大类（可选）。不填则返回全部车型。'},
                'min_load_ton': {'type': 'number', 'description': '最低载重（吨），只返回载重大于等于此值的车型'}}},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=4,
        prompt_line='查看车型库',
        prompt_hint='用户问有哪些车型 / 要推荐车型时调用',
    ),
    CapabilitySpec(
        name='compare_routes',
        description='对比多个运输方案的费用差异。用于帮用户决定选哪个车型、走哪条路线更划算。每个方案分别调用费用引擎计算。',
        parameters={'type': 'object',
 'properties': {'scenarios': {'type': 'array',
                              'items': {'type': 'object',
                                        'properties': {'label': {'type': 'string',
                                                                 'description': "方案名称，如 '13m "
                                                                                "平板车'"},
                                                       'origin': {'type': 'string'},
                                                       'destination': {'type': 'string'},
                                                       'cargo_weight_ton': {'type': 'number'},
                                                       'cargo_type': {'type': 'string'},
                                                       'vehicle_model_id': {'type': 'string'},
                                                       'loading_mode': {'type': 'string'},
                                                       'empty_return': {'type': 'boolean'}},
                                        'required': ['label',
                                                     'origin',
                                                     'destination',
                                                     'cargo_weight_ton']},
                              'description': '要对比的方案列表（至少 2 个）',
                              'minItems': 2,
                              'maxItems': 5}},
 'required': ['scenarios']},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=5,
        prompt_line='多方案对比',
        prompt_hint='用户要对比两条（或多条）路线的成本/时效时调用',
    ),
    CapabilitySpec(
        name='geocode_address',
        description='将地址文本转换为经纬度坐标。用于验证地址是否存在、获取精确坐标。越南地址用越南语。',
        parameters={'type': 'object',
 'properties': {'address': {'type': 'string', 'description': '要查询的地址'}},
 'required': ['address']},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=6,
        prompt_line='地址查询/坐标',
        prompt_hint='需要把地址/地名转成经纬度时调用（算价内部也会自动转）',
    ),
    CapabilitySpec(
        name='query_exchange_rate',
        description="查询今日人民币→越南盾实时汇率。当用户问'汇率''1块钱换多少越南盾''CNY到VND'时调用。返回当前汇率（1 CNY = X VND）及数据来源。",
        parameters={'type': 'object', 'properties': {}},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=7,
        prompt_line='实时汇率（CNY→VND）',
        prompt_hint='用户问今日汇率时调用',
    ),
    CapabilitySpec(
        name='extract_shipping_request',
        description='从用户自然语言运输需求中提取结构化装运单（JobDraft），并**直接填入下方字段**回填前端任务卡。\n\n当用户描述运输需求（发车地、目的地、口岸、货物、车型、要求）时调用。请**逐项**从用户原话提取，不要凭空补全、不要计算；尺寸按用户使用的单位（dim_unit）原样填数字，重量统一填吨。\n\ncargo 每项含：name 货名 / count 数量 / length、width、height（按 dim_unit 的单位填数值）/ weight 单件重量(吨) / type 货型(dangerous|cold_chain|heavy_equipment|normal|oversized|other) / value_vnd 单件货值。\ntext 字段填用户原始文本，供系统在结构化信息不完整时兜底解析。',
        parameters={'type': 'object',
 'properties': {'text': {'type': 'string',
                         'description': "用户原始运输需求文本（兜底用，填原文）。例如：'20吨变压器配件从上海经友谊关到河内，8件每件2.5吨，13米平板，要报价和时效'"},
                'origin': {'type': 'string', 'description': '发车地（如 上海 / 东莞）。'},
                'destination': {'type': 'string', 'description': '目的地（如 河内 / 越南顺化 / 完整收货地址）。'},
                'borderCrossing': {'type': 'string', 'description': '过境口岸（默认友谊关）。'},
                'dim_unit': {'type': 'string',
                             'enum': ['mm', 'cm', 'm'],
                             'description': '用户使用的尺寸单位（mm/cm/m）。机械/设备常为 mm。'},
                'vehicle_preference': {'type': 'string',
                                       'description': '车型偏好（如 17.5米车 / 特种设备车 / 13米平板）。'},
                'loading_mode': {'type': 'string',
                                 'enum': ['full_truck', 'consolidated'],
                                 'description': "整车/拼货（见'拼货/散货/零担'则为 consolidated）。"},
                'requirement': {'type': 'string', 'description': '用户诉求（报价/时效/是否装得下/全程费用）。'},
                'cargo': {'type': 'array',
                          'description': '货物清单；每项 length/width/height 按 dim_unit 单位填数值，weight '
                                         '填单件重量(吨)。',
                          'items': {'type': 'object',
                                    'properties': {'name': {'type': 'string'},
                                                   'count': {'type': 'integer', 'minimum': 1},
                                                   'length': {'type': 'number'},
                                                   'width': {'type': 'number'},
                                                   'height': {'type': 'number'},
                                                   'weight': {'type': 'number',
                                                              'description': '单件重量（吨）'},
                                                   'type': {'type': 'string',
                                                            'description': 'dangerous/cold_chain/heavy_equipment/normal/oversized/other'},
                                                   'value_vnd': {'type': 'number'}},
                                    'required': ['name', 'count']}}},
 'required': ['text']},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=1,
        prompt_line='拆解运输需求为结构化装运单（JobDraft），回填任务卡（场景 A 的第一步）',
        prompt_hint='用户描述运输需求时**第一步且唯一第一步**调用',
    ),
    CapabilitySpec(
        name='query_vehicle_count',
        description='按四约束（重量/体积/长度/面积）核算这批货需要几辆车，并给出分解与主因。当用户问"需要几辆车/为什么N辆车/装不装得下/车辆数"时必须调用，用返回的真实分解回答，绝不能凭空猜一个数字。',
        parameters={'type': 'object',
 'properties': {'cargo_weight_ton': {'type': 'number', 'description': '货物总重（吨）'},
                'volume_m3': {'type': 'number', 'description': '货物总体积（立方米），可选'},
                'cargo_type': {'type': 'string',
                               'description': 'normal/oversized/heavy_equipment/cold_chain/other'},
                'vehicle_model_id': {'type': 'string',
                                     'description': '指定车型（如 flatbed_13m）；不传则系统自动选最小能装下的车'},
                'items': {'type': 'array',
                          'description': '单件货物明细（长件/不可堆叠时必填）',
                          'items': {'type': 'object',
                                    'properties': {'name': {'type': 'string'},
                                                   'count': {'type': 'integer', 'minimum': 1},
                                                   'length_m': {'type': 'number'},
                                                   'width_m': {'type': 'number'},
                                                   'height_m': {'type': 'number'},
                                                   'weight_kg': {'type': 'number'},
                                                   'stackable': {'type': 'boolean',
                                                                 'description': '是否可堆叠（设备/大件=否）'}},
                                    'required': ['length_m', 'width_m']}}},
 'required': ['cargo_weight_ton']},
        kind='read',
        confirm=False,
        roles=('internal', 'customer'),
        prompt_rank=8,
        prompt_line='核算车辆数（四约束分解）',
        prompt_hint='用户问「需要几辆车 / 为什么 N 辆车 / 装不装得下」时**必须**调用，用返回的真实四约束分解回答',
    ),
]
