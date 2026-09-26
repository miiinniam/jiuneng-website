"""v006 第 2 步 · 前端能力（UI 动作）声明。

这些能力的**执行者在前端**（`desktop/renderer/js/actions.js` 的 ACTIONS 表）：
LLM 可以像调工具一样调用它们，但后端**不执行**，而是把调用转成 SSE `action` 事件下发。

规矩：
- `kind="read"`  → 前端立即执行（导航 / 只读，无副作用）
- `kind="write"` → 前端先渲染「确认执行 / 取消」按钮，用户点确认才执行
- `roles=("internal",)` → 打开 `registry.ROLE_ENFORCEMENT` 后，客户角色调用会被拒

加一条前端动作 = 这里加一条声明 + `js/actions.js` 的 `ACTIONS` 里加一项（仅此两处）。
"""
from __future__ import annotations

from app.ai.spec import CapabilitySpec

UI_SPECS: list[CapabilitySpec] = [
    CapabilitySpec(
        name="get_app_state",
        description=(
            "读取软件当前状态：当前步骤、任务卡内容（起终点/货物/车型）、角色、"
            "上次报价、超限标志。回答任何与\"界面里现在是什么\"有关的问题前，先调用它。"
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        kind="read", confirm=False, roles=("internal", "customer"),
        prompt_rank=101, prompt_line="读取界面当前状态（任务卡 / 步骤 / 上次报价）",
        prompt_hint="不确定界面现状时先调用",
        locality="frontend",
    ),
    CapabilitySpec(
        name="goto_step",
        description="切换界面视图：confirm（任务卡）/ result（结果与报价单）/ loading（装车 3D）。只切换显示，不改数据。",
        parameters={
            "type": "object",
            "properties": {
                "step": {"type": "string", "enum": ["confirm", "result", "loading"],
                         "description": "目标视图"},
            },
            "required": ["step"],
        },
        kind="read", confirm=False, roles=("internal", "customer"),
        prompt_rank=102, prompt_line="切换视图（任务卡 / 结果 / 装车 3D）",
        prompt_hint="用户说\"回到任务卡\"\"看结果\"\"看报价单\"时调用",
        locality="frontend",
    ),
    CapabilitySpec(
        name="open_loading_3d",
        description="打开装车 3D 视图（需已有计算结果）。",
        parameters={"type": "object", "properties": {}, "required": []},
        kind="read", confirm=False, roles=("internal", "customer"),
        prompt_rank=103, prompt_line="打开装车 3D 视图",
        prompt_hint="用户说\"装车图\"\"怎么装\"\"看下装得下吗\"时调用（需先有结果）",
        locality="frontend",
    ),
    CapabilitySpec(
        name="fill_job_draft",
        description=(
            "把结构化运输需求回填到任务卡（发车地/目的地/口岸/货物明细/车型偏好）。"
            "字段与 extract_shipping_request 的 JobDraft 一致："
            "origin / destination / borderCrossing / dim_unit / vehicle_preference / loading_mode / requirement / cargo[]。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "draft": {
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string"},
                        "destination": {"type": "string"},
                        "borderCrossing": {"type": "string"},
                        "dim_unit": {"type": "string", "enum": ["mm", "cm", "m"]},
                        "vehicle_preference": {"type": "string"},
                        "loading_mode": {"type": "string", "enum": ["full_truck", "consolidated"]},
                        "requirement": {"type": "string"},
                        "cargo": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"}, "count": {"type": "integer"},
                                    "length": {"type": "number"}, "width": {"type": "number"},
                                    "height": {"type": "number"}, "weight": {"type": "number"},
                                    "type": {"type": "string"}, "value_vnd": {"type": "number"},
                                },
                            },
                        },
                    },
                    "required": ["origin", "destination"],
                },
            },
            "required": ["draft"],
        },
        kind="write", confirm=False, roles=("internal", "customer"),
        prompt_rank=104, prompt_line="回填任务卡（结构化装运单 → 界面字段）",
        prompt_hint="需要把需求写进任务卡时调用（与 extract_shipping_request 等价，二选一）",
        locality="frontend",
    ),
    CapabilitySpec(
        name="run_quote",
        description="按任务卡当前内容执行计算（路线 + 费用 + 车数 + 多方案），并把界面切到结果视图。",
        parameters={"type": "object", "properties": {}, "required": []},
        kind="write", confirm=False, roles=("internal", "customer"),
        prompt_rank=105, prompt_line="执行计算（等于用户点【开始计算】）",
        prompt_hint="用户说\"算一下\"\"开始计算\"\"报价\"且任务卡已就绪时调用",
        locality="frontend",
    ),
    CapabilitySpec(
        name="select_vehicle_model",
        description="选择车型（含大件/超限车型）。model_id 必须来自车型库（先调 query_vehicle_models 取）。",
        parameters={
            "type": "object",
            "properties": {"model_id": {"type": "string", "description": "车型 ID，如 flatbed_13m / special_axle_100t"}},
            "required": ["model_id"],
        },
        kind="write", confirm=False, roles=("internal", "customer"),
        prompt_rank=106, prompt_line="选择车型（含大件/超限车型）",
        prompt_hint="用户确认要某个车型时调用",
        locality="frontend",
    ),
    CapabilitySpec(
        name="set_role",
        description="切换视角：internal（内部：成本+利润+售价）/ customer（客户：只看售价）。",
        parameters={
            "type": "object",
            "properties": {"role": {"type": "string", "enum": ["internal", "customer"]}},
            "required": ["role"],
        },
        # ⚠️ 两种角色都允许：set_role 只是**视图切换**，MVP 本就免密码（顶栏可点）。
        #    拦它只制造死胡同（客户视角下 AI 无法切回）；硬保护靠 ①客户快照不含成本/利润
        #    ②set_pricing / set_oversize_trip_fee / save_border_fees_default 仍 internal-only。
        kind="write", confirm=False, roles=("internal", "customer"),
        prompt_rank=107, prompt_line="切换内部 / 客户视角",
        prompt_hint="用户说\"切客户视角\"\"内部看成本\"时调用",
        locality="frontend",
    ),
    CapabilitySpec(
        name="set_pricing",
        description="设置本次报价的毛利率（百分数，如 15 表示 15%）。仅内部视角可用，需用户确认。",
        parameters={
            "type": "object",
            "properties": {"margin_rate_pct": {"type": "number", "description": "0–95 的百分数"}},
            "required": ["margin_rate_pct"],
        },
        kind="write", confirm=True, roles=("internal",),
        prompt_rank=108, prompt_line="设置毛利率（内部，需确认）",
        prompt_hint="用户说\"毛利率改成 X%\"时调用；必须复述将要设置的值",
        locality="frontend",
    ),
    CapabilitySpec(
        name="set_oversize_trip_fee",
        description="录入大件/超限的专线趟价（VND，整数）。该金额直出报价单、不进成本模型。需用户确认。",
        parameters={
            "type": "object",
            "properties": {"trip_fee_vnd": {"type": "number", "description": "专线趟价（越南盾）"}},
            "required": ["trip_fee_vnd"],
        },
        kind="write", confirm=True, roles=("internal",),
        prompt_rank=109, prompt_line="录入大件专线趟价（需确认）",
        prompt_hint="超限单（单件 > 常规车型上限）用户给了专线价时调用",
        locality="frontend",
    ),
    CapabilitySpec(
        name="export_quote_docx",
        description="生成并下载正式 docx 报价单（内部版含成本/利润，客户版只看售价）。需用户确认。",
        parameters={"type": "object", "properties": {}, "required": []},
        kind="write", confirm=True, roles=("internal", "customer"),
        prompt_rank=110, prompt_line="生成正式报价单 docx（需确认）",
        prompt_hint="用户说\"出报价单\"\"导出\"时调用（需先有结果）",
        locality="frontend",
    ),
    CapabilitySpec(
        name="save_border_fees_default",
        description="把当前口岸费编辑器的值保存为**默认值**（写回 fixed_fees.json，影响以后所有报价）。需用户确认。",
        parameters={"type": "object", "properties": {}, "required": []},
        kind="write", confirm=True, roles=("internal",),
        prompt_rank=111, prompt_line="保存口岸费为默认（写库，需确认）",
        prompt_hint="用户明确说\"存成默认\"时才调用；调用前必须复述会写库",
        locality="frontend",
    ),
]
