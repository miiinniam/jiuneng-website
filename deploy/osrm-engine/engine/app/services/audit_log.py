"""AI 能力调用审计（v006 第 1 步）。

每次能力调用落一条 JSONL 到 `data_dir()/ai_audit.jsonl`：
`{ts, role, tool, ok, note, args}`

设计原则：**审计失败绝不影响业务** —— 整个写入包在 try/except 里，只吞不抛。
报价/费率这类会引纠纷的动作，未来靠这个文件回放"谁在什么时候调了什么、改了什么"。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services._paths import data_dir

AUDIT_FILE_NAME = "ai_audit.jsonl"
_MAX_VALUE_LEN = 200


def audit_path() -> Path:
    """审计文件路径（测试里 monkeypatch 本函数即可重定向）。"""
    return Path(data_dir()) / AUDIT_FILE_NAME


def _shrink(value: Any) -> Any:
    """把参数裁到可审计的体积：字符串截断，容器只保留浅层。"""
    if isinstance(value, str):
        return value if len(value) <= _MAX_VALUE_LEN else value[:_MAX_VALUE_LEN] + "…"
    if isinstance(value, dict):
        return {str(k): _shrink(v) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [_shrink(v) for v in list(value)[:10]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_VALUE_LEN]


def log_call(*, tool: str, role: str, ok: bool, args: dict | None = None, note: str = "") -> None:
    """追加一条审计记录。任何异常都被吞掉（审计不许拖垮业务）。"""
    try:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "role": role,
            "tool": tool,
            "ok": bool(ok),
            "note": note,
            "args": _shrink(args or {}),
        }
        p = audit_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 —— 审计永远不许抛
        return
