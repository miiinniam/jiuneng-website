#!/usr/bin/env python
"""图位覆盖与来源门禁（v9）。

断言四件事，任一失败 exit 1：
  1. 来源门禁：两个 build 脚本的源图**全部**出自 `优质素材/`（用户 2026-11-19 指定）；
  2. 全量覆盖：`优质素材/` 里 34 张照片 + 3 段视频，逐一被某个图位引用（不许剩）；
  3. 产物存在：脚本声明的每个输出文件都已生成；
  4. 代码对位：`src/site/content.ts` 里出现的每个 /assets/ 路径都在磁盘上存在（防静默 404）。

用法：env -u PYTHONPATH python scripts/check-photo-coverage.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "public" / "assets" / "真实项目图片" / "优质素材"
PUBLIC = ROOT / "public"
CONTENT = ROOT / "src" / "site" / "content.ts"


def rows(script: str) -> list[tuple[str, str]]:
    """从 build 脚本的槽位表里抠出 (输出, 源图) 对。"""
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    pairs = re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)"', text)
    return [(a, b) for a, b in pairs if b.endswith((".jpg", ".png", ".mp4"))]


def img_rows(script: str) -> list[tuple[str, str]]:
    return [(a, b) for a, b in rows(script) if b.endswith((".jpg", ".png"))]


def vid_rows(script: str) -> list[tuple[str, str]]:
    return [(a, b) for a, b in rows(script) if b.endswith(".mp4")]


def main() -> int:
    fails: list[str] = []

    slots = img_rows("build-photo-slots.py") + img_rows("build-photo-v9.py")
    vids = vid_rows("build-photo-v9.py")
    if not slots:
        print("X 没从 build 脚本里解析到任何槽位（正则失配？），门禁视为失败")
        return 1

    # 1. 来源门禁
    bad = [(a, b) for a, b in slots + vids if not b.startswith("优质素材/")]
    for a, b in bad:
        fails.append(f"来源越界：{a} ← {b}（只允许 优质素材/）")

    # 2. 全量覆盖
    lib_imgs = {p.name for p in LIB.glob("*.jpg")} | {p.name for p in LIB.glob("*.png")}
    lib_vids = {p.name for p in LIB.glob("*.mp4")}
    used = {Path(b).name for _, b in slots + vids}
    for name in sorted(lib_imgs | lib_vids):
        if name not in used:
            fails.append(f"素材未被任何图位使用：{name}")

    # 3. 产物存在
    for out, _ in slots:
        target = PUBLIC / "assets" / ("v9" if out.startswith("cat-") or "/" in out else "v8") 
        # v8 槽位只有文件名，v9 槽位带子目录（cat-*/main.jpg、video/*.mp4）
        path = (PUBLIC / "assets" / "v9" / out) if out.startswith(("cat-", "video/")) else (PUBLIC / "assets" / "v8" / f"{out}.jpg")
        if not path.exists():
            fails.append(f"产物缺失：{path.relative_to(ROOT)}")

    # v9 视频的输出名与源名不同，单独核对
    for name in ("loading-drill-rig", "port-crane-day", "floating-crane-night"):
        for ext in ("mp4", "jpg"):
            p = PUBLIC / "assets" / "v9" / "video" / f"{name}.{ext}"
            if not p.exists():
                fails.append(f"视频产物缺失：{p.relative_to(ROOT)}")

    # 4. 代码对位
    refs = set(re.findall(r"'(/assets/[^']+)'", CONTENT.read_text(encoding="utf-8")))
    if not refs:
        fails.append("content.ts 里没有 /assets/ 引用（解析失败？）")
    for ref in sorted(refs):
        if not (PUBLIC / ref.lstrip("/")).exists():
            fails.append(f"content.ts 引用不存在：{ref}")

    # 统计
    n_img = len(lib_imgs)
    n_vid = len(lib_vids)
    print(f"槽位 {len(slots)} 条 · 素材 {n_img} 图 + {n_vid} 视频 · content.ts 引用 {len(refs)} 个")
    if fails:
        print("\n失败：")
        for f in fails:
            print("  X", f)
        return 1
    print("全部通过：来源全在 优质素材/，素材零剩余，产物齐全，引用无 404")
    return 0


if __name__ == "__main__":
    sys.exit(main())
