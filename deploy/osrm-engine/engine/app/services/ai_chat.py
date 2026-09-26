"""
OSRM++ AI 对话编排引擎
======================

处理多轮对话的 Tool Calling 循环：
1. 用户消息 → DeepSeek（带工具定义）
2. DeepSeek 返回 text 或 tool_calls
3. 如果是 tool_calls → 执行工具 → 把结果追加到 messages → 回到步骤 1
4. 如果是 text → 流式输出到前端

防无限循环：
- 连续 tool call 超过 3 轮 → 强制要求模型给出最终答案
- tool call 前的闲聊文本不输出（"好的，我来算..." 等）
- 总轮次上限 20 轮

作为 async generator，yield SSE 事件 dict:
  {"event": "tool_start", "data": {"name": "...", "params": {...}}}
  {"event": "tool_done",  "data": {"name": "...", "result": {...}}}
  {"event": "action",     "data": {"action": "...", "args": {...}, "kind": "...", "confirm": bool, "id": "..."}}
  {"event": "text",       "data": {"content": "..."}}
  {"event": "error",      "data": {"message": "..."}}
  {"event": "done",       "data": {"usage": {...}}}

🆕 v006：前端动作（`registry.is_frontend(name)` 为真）**不在后端执行** —— 改为下发 `action` 事件，
由界面（desktop/renderer/js/actions.js）执行后把新状态快照随下一轮消息带回。
"""

import json
from typing import AsyncGenerator

from app.ai import registry
from app.services.ai_client import StreamChunk, astream_chat
from app.services.ai_chat_prompt import OSRM_CHAT_SYSTEM, app_state_block
from app.services.ai_tools import execute_tool

MAX_TOOL_ROUNDS = 20       # 总轮次上限
MAX_CONSECUTIVE_TOOLS = 5  # 连续 tool call 上限，超过后强制要求回答


async def run_chat(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    app_state: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """运行多轮对话（自动处理 tool calling 循环），yield SSE 事件。

    🆕 v006：前端动作（registry.is_frontend）不执行，改 yield `action` 事件交给界面。
    """

    full_messages = list(messages)
    system = OSRM_CHAT_SYSTEM + app_state_block(app_state)
    # 🆕 前端动作的角色硬拦依据（取快照里的 role；缺省视为内部）
    frontend_role = str((app_state or {}).get("role") or "internal")
    tool_rounds = 0
    consecutive_tools = 0  # 连续 tool call 计数

    while tool_rounds < MAX_TOOL_ROUNDS:
        tool_rounds += 1

        # 如果连续 tool call 太多，注入强制回答提示
        if consecutive_tools >= MAX_CONSECUTIVE_TOOLS:
            full_messages.append({
                "role": "user",
                "content": (
                    "你已经调用了足够多的工具，数据已经齐全。"
                    "现在请直接给出最终回答：列出费用明细、总价、路线分析和建议。"
                    "不要再说「好的，我来计算」之类的话，直接输出结果。"
                    "如果某个工具返回了错误，请根据已有的正确数据给出最佳估算并注明。"
                ),
            })
            consecutive_tools = 0  # 重置，给最后一次机会

        tool_calls_buffer: list[dict] = []
        text_buffer: list[str] = []

        # 流式调用 DeepSeek
        async for chunk in astream_chat(
            full_messages,
            system=system,
            tools=registry.tool_schemas() if consecutive_tools < MAX_CONSECUTIVE_TOOLS else None,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.finish_reason == "tool_calls":
                tool_calls_buffer = chunk.tool_calls
                break
            elif chunk.delta_content:
                text_buffer.append(chunk.delta_content)

        # 如果有工具调用
        if tool_calls_buffer:
            consecutive_tools += 1

            # 把 assistant 的 tool_calls 消息追加到对话
            # 注意：不保留 tool call 前的闲聊文本（如"好的，我来算..."）
            full_messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_buffer,
            })

            # 执行每个工具
            for tc in tool_calls_buffer:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}

                if registry.is_frontend(fn_name):
                    # 🆕 前端动作：后端不执行，下发 action 事件，由界面执行并回传状态。
                    # ⚠️ 角色硬拦同样适用于前端动作 —— 否则客户视角能改毛利率/写库
                    #    （registry.ROLE_ENFORCEMENT 只保护后端 invoke()，这条下发路径必须自己查）。
                    spec = registry.get(fn_name)
                    if (registry.ROLE_ENFORCEMENT and spec and frontend_role not in spec.roles):
                        result_str = json.dumps(
                            {"error": f"当前角色（{frontend_role}）无权调用 {fn_name}。"
                                      f"该动作仅限 {list(spec.roles)}，请让内部人员在内部视角下操作。"},
                            ensure_ascii=False,
                        )
                        yield {"event": "tool_done",
                               "data": {"name": fn_name, "result": json.loads(result_str)}}
                    else:
                        yield {
                            "event": "action",
                            "data": {
                                "action": fn_name,
                                "args": fn_args,
                                "kind": (spec.kind if spec else "write"),
                                "confirm": bool(spec.confirm) if spec else True,
                                "id": tc["id"],
                            },
                        }
                        # 🆕 同一轮内的依赖动作：set_role 成功后，后续动作按"目标角色"判定 ——
                        #    否则"切回内部 + 改毛利率"这类连招会被本轮开始时的过期快照误拦
                        #    （实测：AI 一轮内先 set_role 再 set_pricing，后者被当成 customer 拒掉）。
                        if fn_name == "set_role" and fn_args.get("role") in ("internal", "customer"):
                            frontend_role = fn_args["role"]
                        result_str = json.dumps(
                            {"status": "dispatched_to_ui", "action": fn_name,
                             "note": "已下发界面执行；界面执行后会把新状态快照随下一轮消息带来。"
                                     "若用户还需点「确认执行」，请提醒他确认。"},
                            ensure_ascii=False,
                        )
                else:
                    yield {
                        "event": "tool_start",
                        "data": {"name": fn_name, "params": fn_args},
                    }

                    result_str = await execute_tool(fn_name, fn_args)
                    try:
                        result_data = json.loads(result_str)
                    except json.JSONDecodeError:
                        result_data = {"raw": result_str}

                    yield {
                        "event": "tool_done",
                        "data": {"name": fn_name, "result": result_data},
                    }

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })

            continue

        # 没有工具调用 — 流式输出缓冲的文本
        consecutive_tools = 0  # 重置
        for text in text_buffer:
            yield {"event": "text", "data": {"content": text}}
        break

    else:
        yield {
            "event": "error",
            "data": {"message": "对话轮次超限，请重新提问"},
        }

    yield {
        "event": "done",
        "data": {"usage": {}},
    }
