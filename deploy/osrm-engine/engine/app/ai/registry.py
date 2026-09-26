"""v006 能力注册表 · 生成与调度。

唯一真源 = `app/ai/spec.py`（后端能力，生成产物）+ `app/ai/ui_spec.py`（前端动作，手写），
本模块把两者合并成统一的 `SPECS` 并对外出口：

| 出口 | 消费者 |
|---|---|
| `tool_schemas()` | LLM 的 tools 参数（`ai_chat.py`）；`locality="backend"` 只取后端工具 |
| `tools_prompt_block()` | 系统提示里的后端工具清单（`ai_chat_prompt.py`）|
| `ui_actions_prompt_block()` | 系统提示里「你可以操作软件界面」段的清单 |
| `is_frontend()` | 前端动作判定（`ai_chat.py`：不执行，转 `action` 事件下发）|
| `invoke()` | **唯一执行入口**：权限 → 前端拦截 → 确认 → 审计 → 执行（`ai_tools.execute_tool` 薄壳委托）|
| `register_executor()` | `ai_tools.py` 在 import 末尾把执行器挂进来（避免循环导入）|

设计要点：
- **加能力只改 `spec.py`（后端）或 `ui_spec.py`（前端）+ 注册一个执行器**，schema / 提示清单 / 权限 / 审计自动跟上。
- `invoke()` 是唯一的收口点：错误语义与重构前保持一致（未知工具 / 异常都返回 JSON 字符串）。
- 权限按角色：`ROLE_ENFORCEMENT` 打开后生效（v006 第 3 步已打开）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from app.ai.spec import SPECS as BACKEND_SPECS, CapabilitySpec
from app.ai.ui_spec import UI_SPECS
from app.services.audit_log import log_call

# 🚩 v006 第 3 步已打开：按 roles 硬拦（客户角色改价/写库直接拒）
ROLE_ENFORCEMENT = True

# 能力声明 = 后端（spec.py，生成产物）+ 前端（ui_spec.py，手写）
SPECS: list[CapabilitySpec] = list(BACKEND_SPECS) + list(UI_SPECS)

# 能力名 → 执行器（由 ai_tools.py 注册）
EXECUTORS: dict[str, Callable[[dict], Any]] = {}

_BY_NAME: dict[str, CapabilitySpec] = {s.name: s for s in SPECS}

# 提示词清单排序（与 v005 系统提示逐行一致，见 spec.prompt_rank）
_PROMPT_ORDER = sorted([s for s in SPECS if s.locality == "backend"],
                       key=lambda s: (s.prompt_rank, s.name))
_UI_PROMPT_ORDER = sorted([s for s in SPECS if s.locality == "frontend"],
                          key=lambda s: (s.prompt_rank, s.name))


def names() -> list[str]:
    """全部能力名（= tool_schemas 的顺序）。"""
    return [s.name for s in SPECS]


def get(name: str) -> CapabilitySpec | None:
    return _BY_NAME.get(name)


def is_known(name: str) -> bool:
    return name in _BY_NAME


def register_executor(name: str, fn: Callable[[dict], Any]) -> None:
    """把执行器挂到某个已声明的能力上。未声明的名字立刻报错（防漏声明）。"""
    if name not in _BY_NAME:
        raise KeyError(f"未在 app/ai/spec.py 声明的能力: {name}")
    EXECUTORS[name] = fn


# 执行器签名是否接受「args」入参（缓存；见 _call_executor 的为何需要）
_ACCEPTS_ARGS: dict[str, bool] = {}


def _accepts_args(fn: Callable) -> bool:
    import inspect

    key = getattr(fn, "__qualname__", repr(fn))
    if key in _ACCEPTS_ARGS:
        return _ACCEPTS_ARGS[key]
    try:
        names = [
            p for p in inspect.signature(fn).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        ok = len(names) >= 1
    except (TypeError, ValueError):      # C 函数 / 内建：无法反射 → 按需要入参处理
        ok = True
    _ACCEPTS_ARGS[key] = ok
    return ok


def _call_executor(fn: Callable, args: dict) -> Any:
    """统一调用执行器。

    ⚠️ 加这层是因为 v007 实测踩到：`ai_tools._query_exchange_rate()` 当时写成**零参数**，
    而这里统一 `fn(args)` 调用 → AI 面板问汇率直接报
    `_query_exchange_rate() takes 0 positional arguments but 1 was given`。
    现在签名不匹配不再炸掉工具，但仍要求新执行器写上 `args`（测试会拦）。
    """
    return fn(args) if _accepts_args(fn) else fn()


def tool_schemas(*, locality: str | None = None) -> list[dict]:
    """喂给 LLM 的 tools。

    locality=None → 全部能力（后端工具 + 前端动作），ai_chat 用这个；
    locality="backend" → 仅后端工具（等价性测试 + ai_tools.TOOLS 用）。
    """
    items = [s for s in SPECS if locality is None or s.locality == locality]
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            },
        }
        for s in items
    ]


def is_frontend(name: str) -> bool:
    spec = get(name)
    return bool(spec and spec.locality == "frontend")


def ui_actions_prompt_block() -> str:
    """系统提示里「你可以操作界面」那段的清单（由声明生成）。"""
    return "\n".join(
        f"{i}. **{s.name}** — {s.prompt_line}"
        for i, s in enumerate(_UI_PROMPT_ORDER, start=1)
    )


def tools_prompt_block() -> str:
    """系统提示里的工具清单（由声明生成，顺序与旧提示一致）。"""
    return "\n".join(
        f"{i}. **{s.name}** — {s.prompt_line}"
        for i, s in enumerate(_PROMPT_ORDER, start=1)
    )


async def invoke(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    role: str = "internal",
    confirmed: bool = False,
) -> str:
    """**唯一执行入口**：未知工具 → 权限 → 确认 → 审计 → 执行（异常统一转 JSON error）。

    返回值为字符串（执行器的原始输出），与重构前 `execute_tool` 的契约一致。
    """
    args = arguments or {}
    spec = get(name)
    if spec is None:
        log_call(tool=name, role=role, ok=False, args=args, note="unknown_tool")
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

    if ROLE_ENFORCEMENT and role not in spec.roles:
        log_call(tool=name, role=role, ok=False, args=args, note="role_denied")
        return json.dumps(
            {"error": f"当前角色（{role}）无权调用 {name}"}, ensure_ascii=False
        )

    if spec.locality == "frontend":
        log_call(tool=name, role=role, ok=True, args=args, note="frontend_dispatched")
        return json.dumps(
            {"status": "frontend_action", "action": name,
             "message": "该能力由界面执行，后端只负责下发"},
            ensure_ascii=False,
        )

    if spec.confirm and not confirmed:
        log_call(tool=name, role=role, ok=False, args=args, note="needs_confirm")
        return json.dumps(
            {"status": "needs_confirm", "tool": name, "message": "该操作需用户确认后执行"},
            ensure_ascii=False,
        )

    fn = EXECUTORS.get(name)
    if fn is None:
        log_call(tool=name, role=role, ok=False, args=args, note="no_executor")
        return json.dumps({"error": f"工具未注册执行器: {name}"}, ensure_ascii=False)

    try:
        out = _call_executor(fn, args)
        if asyncio.iscoroutine(out):
            out = await out
        log_call(tool=name, role=role, ok=True, args=args)
        return out
    except Exception as e:  # noqa: BLE001 —— 与重构前 execute_tool 的错误语义一致
        log_call(tool=name, role=role, ok=False, args=args, note=f"error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
