#!/usr/bin/env python
"""AI 询价功能「源码锁定」基线工具。

用途：大改流程之前先把相关文件钉成清单 + sha256 指纹，改完能一键回答
「到底动了哪些文件、有没有动到锁定范围之外」。

用法：
    python scripts/ai-scope.py --write    # 生成/刷新基线 docs/ai-inquiry/ai-scope.lock.json
    python scripts/ai-scope.py --check    # 与基线比对：changed / missing / out-of-scope
    python scripts/ai-scope.py --list     # 只打印清单

约定：
- 清单里的路径一律 POSIX 相对路径（仓库根起）。
- 「out-of-scope」= git 工作区里有改动但不在清单里的文件，只做提示不做失败判定
  （并行开发常有无关改动，工具只负责把它念出来）。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "docs" / "ai-inquiry" / "ai-scope.lock.json"

# ── 锁定范围 ────────────────────────────────────────────────
# A 站内测算助手：全站悬浮 + /platform/assistant + 旧 /ai 页，共用 /api/agent-chat
SCOPE: dict[str, list[str]] = {
    "A1 · 对话编排与工具（服务端）": [
        "server/agentChat.ts",
        "server/osrmQuote.ts",
        "server/tools/customs.ts",
        "server/tools/fleet.ts",
        "server/tools/engineClient.ts",
        "server/leads.ts",
        "server/env.ts",
    ],
    "A2 · HTTP 入口（server.ts 内）": [
        "server.ts",
    ],
    "A3 · 悬浮助手前端": [
        "src/tools/AssistantLauncher.tsx",
        "src/tools/chat.ts",
        "src/styles/tools-assistant.css",
        "src/shell/Layout.tsx",
        "src/shell/TopBar.tsx",
        "src/content/zh/assistant.ts",
        "src/content/vi/assistant.ts",
        "src/content/en/assistant.ts",
    ],
    "A4 · 助手独立页与工具页": [
        "src/tools/assistant-page.tsx",
        "src/tools/routing.tsx",
        "src/tools/RoutingForm.tsx",
        "src/tools/customs.tsx",
        "src/tools/CustomsForm.tsx",
        "src/tools/fleet.tsx",
        "src/tools/FleetForm.tsx",
        "src/tools/api.ts",
        "src/tools/parts.tsx",
        "src/tools/LeadModal.tsx",
    ],
    "A5 · 口径与内容（服务端也 import）": [
        "src/agent/content.ts",
        "src/agent/quoteIntel.ts",
    ],
    "A6 · 旧 /ai 页（同端点第二套面板）": [
        "src/agent/App.tsx",
        "src/agent/ChatPanel.tsx",
        "src/agent/main.tsx",
        "src/agent/styles.css",
        "ai.html",
    ],
    "B1 · /quote 报价工作台助手（前端）": [
        "features/quote/src/components/ai/ChatPanel.tsx",
        "features/quote/src/components/ai/RichText.tsx",
        "features/quote/src/components/ai/parseRichText.ts",
        "features/quote/src/components/ai/extractCoords.ts",
        "features/quote/src/components/workspace/WorkspacePanel.tsx",
        "features/quote/src/components/workspace/plan.ts",
        "features/quote/src/components/workspace/parseHints.ts",
        "features/quote/src/pages/QuoteApp.tsx",
        "features/quote/src/api.ts",
        "features/quote/src/state/useQuoteForm.ts",
        "features/quote/src/i18n/workspace.ts",
        "features/quote/src/i18n/panels.ts",
        "features/quote/src/i18n/strings.ts",
    ],
    "B2 · /quote 代理（服务端）": [
        "server/quoteProxy.ts",
    ],
    "C · 验收脚本": [
        "scripts/verify-chat-deepseek.py",
        "scripts/verify-chat-robust.py",
        "scripts/verify-chat-render.py",
        "scripts/probe-chat-live.py",
        "scripts/probe-tools.ts",
        "scripts/verify-agent-page.py",
        "scripts/verify-quote-page.py",
        "scripts/probe-quote-api.py",
        "scripts/verify-quote-timeout.py",
    ],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_files() -> list[str]:
    seen: list[str] = []
    for group in SCOPE.values():
        for rel in group:
            if rel not in seen:
                seen.append(rel)
    return seen


def snapshot() -> dict:
    files: dict[str, dict] = {}
    for rel in all_files():
        p = ROOT / rel
        if not p.exists():
            files[rel] = {"exists": False}
            continue
        data = p.read_bytes()
        files[rel] = {
            "exists": True,
            "sha256": sha(p),
            "bytes": len(data),
            "lines": data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1),
        }
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    return {"head": head, "files": files}


def load_lock() -> dict | None:
    if not LOCK.exists():
        return None
    return json.loads(LOCK.read_text(encoding="utf-8"))


def git_dirty() -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    dirty: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        dirty.append(path.strip('"').replace("\\", "/"))
    return dirty


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for group, items in SCOPE.items():
            print(f"\n{group}")
            for rel in items:
                print(f"  {rel}")
        print(f"\n共 {len(all_files())} 个文件")
        return 0

    snap = snapshot()

    if "--write" in argv:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        missing = [r for r, m in snap["files"].items() if not m["exists"]]
        print(f"基线已写入 {LOCK.relative_to(ROOT)}  (HEAD {snap['head'][:7]})")
        print(f"文件 {len(snap['files'])} 个" + (f"，缺失 {len(missing)}：{missing}" if missing else ""))
        return 0

    if "--check" in argv:
        lock = load_lock()
        if lock is None:
            print("没有基线，先跑 --write", file=sys.stderr)
            return 2
        changed, missing, added = [], [], []
        for rel, meta in lock["files"].items():
            cur = snap["files"].get(rel, {"exists": False})
            if not cur.get("exists"):
                missing.append(rel)
            elif not meta.get("exists") or cur["sha256"] != meta.get("sha256"):
                changed.append(rel)
        for rel in snap["files"]:
            if rel not in lock["files"]:
                added.append(rel)

        scoped = set(all_files())
        outside = [p for p in git_dirty() if p not in scoped and not p.startswith("docs/ai-inquiry/")]

        print(f"基线 HEAD {lock['head'][:7]} / 当前 HEAD {snap['head'][:7]}")
        print(f"锁定文件 {len(lock['files'])} 个")
        print(f"changed : {len(changed)}")
        for r in changed:
            print(f"  ~ {r}")
        print(f"missing : {len(missing)}")
        for r in missing:
            print(f"  - {r}")
        print(f"added   : {len(added)}")
        for r in added:
            print(f"  + {r}")
        print(f"锁定范围外的工作区改动 : {len(outside)}（仅提示）")
        for p in outside[:20]:
            print(f"  ? {p}")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
