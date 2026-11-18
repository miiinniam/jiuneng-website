#!/usr/bin/env python
"""校验 public/assets/v7 下投放的照片：缺哪张、尺寸/比例/体积是否达标。

用法：
    python scripts/check-photos.py            # 只看必填 10 张
    python scripts/check-photos.py --all      # 连可选的 4 张一起看
    python scripts/check-photos.py --dir public/assets/v7

退出码：0 全部达标；1 有缺失或不合格（便于挂进构建门禁）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("需要 Pillow：uv pip install pillow 或 pip install pillow")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent

# (相对路径, 目标宽, 目标高, 体积上限 KB, 说明, 是否必填)
REQUIRED = [
    ("01-hero/hero-main.jpg", 2000, 1200, 350, "首页首屏 · 中越干线工程重卡", True),
    ("02-services/services-electric.jpg", 2000, 1200, 350, "服务页 · 电力设备运输", True),
    ("03-fleet/fleet-wind-truck.jpg", 1680, 1120, 300, "设备 · 风机运输特种车", True),
    ("03-fleet/fleet-blade-lifter.jpg", 1680, 1120, 300, "设备 · 叶片举升车", True),
    ("03-fleet/fleet-support.jpg", 1680, 1120, 300, "设备 · 配套运输资源", True),
    ("04-projects/project-metro-hn.jpg", 1680, 1120, 300, "项目 · 河内地铁 1 号线", True),
    ("04-projects/project-metro-hcm.jpg", 1680, 1120, 300, "项目 · 胡志明二号线", True),
    ("04-projects/project-wind.jpg", 1680, 1120, 300, "项目 · 越南风电", True),
    ("05-about/about-border-truck.jpg", 2000, 1200, 350, "关于页 · 口岸/跨境干线", True),
    ("06-contact/contact-fleet.jpg", 2000, 1200, 350, "联系页 · 车队收尾", True),
]

OPTIONAL = [
    ("05-about/about-office.jpg", 1680, 1120, 300, "可选 · 办公室/团队", False),
    ("05-about/about-team-site.jpg", 1680, 1120, 300, "可选 · 现场作业", False),
    ("02-services/services-customs.jpg", 1680, 1120, 300, "可选 · 报关场景", False),
    ("04-projects/project-power.jpg", 1680, 1120, 300, "可选 · 电力项目就位", False),
]


def check(base: Path, rows, verbose: bool) -> tuple[int, int, int]:
    ok = missing = bad = 0
    for rel, tw, th, max_kb, label, required in rows:
        path = base / rel
        if not path.exists():
            missing += 1 if required else 0
            state = "缺失(必填)" if required else "未提供(可选)"
            print(f"  ✗ {rel:42s} {state:12s} {label}")
            continue
        try:
            with Image.open(path) as img:
                w, h = img.size
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"  ✗ {rel:42s} 打不开：{exc}")
            continue
        kb = path.stat().st_size / 1024
        problems = []
        if kb > max_kb:
            problems.append(f"体积 {kb:.0f}KB > {max_kb}KB")
        target_ratio = tw / th
        ratio = w / h if h else 0
        if abs(ratio - target_ratio) > 0.02:
            problems.append(f"比例 {ratio:.2f} ≠ {target_ratio:.2f}")
        if w < tw * 0.8 or h < th * 0.8:
            problems.append(f"分辨率 {w}x{h} 偏小（目标 {tw}x{th}）")
        if problems:
            bad += 1
            print(f"  ! {rel:42s} {w}x{h} {kb:6.0f}KB  " + "；".join(problems))
        else:
            ok += 1
            if verbose:
                print(f"  ✓ {rel:42s} {w}x{h} {kb:6.0f}KB  {label}")
    return ok, missing, bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="public/assets/v7", help="照片根目录")
    ap.add_argument("--all", action="store_true", help="连可选项一起检查")
    ap.add_argument("--verbose", action="store_true", help="达标项也打印")
    args = ap.parse_args()

    base = (ROOT / args.dir) if not Path(args.dir).is_absolute() else Path(args.dir)
    if not base.exists():
        print(f"目录不存在：{base}")
        return 1

    rows = REQUIRED + (OPTIONAL if args.all else [])
    print(f"检查目录：{base}")
    ok, missing, bad = check(base, rows, args.verbose)
    total = len(rows)
    print(f"\n合计 {total} 项：达标 {ok} / 缺失(必填) {missing} / 不合格 {bad}")
    if missing or bad:
        print("处理：按 docs/图片清单与规格.md 补齐或重命名；体积超标用")
        print("      python scripts/optimize-images.py <原图> --as hero|card --out v7/<子目录>/<文件名>")
        return 1
    print("全部达标，可以直接接站点。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
