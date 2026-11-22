#!/usr/bin/env python
"""把「真实项目图片」素材库里的选定照片落成站点用的 v8 图位。

为什么单独一个脚本：
  `optimize-images.py` 是按「用途规格」落的（hero/card/solution），
  但 v8 首页改成「图文对开 + 现场照片带」，每个图位尺寸不同，
  而源图尺寸差异很大（917 宽的轴线特写到 3840 宽的口岸照）。
  集中在一张表里管，换图只改 src 一列，不用记规格。

用法：
    env -u PYTHONPATH python scripts/build-photo-slots.py            # 全部
    env -u PYTHONPATH python scripts/build-photo-slots.py --only fleet-    # 只跑某前缀
    env -u PYTHONPATH python scripts/build-photo-slots.py --dry-run

规则：
  - 源图永远是 public/assets/真实项目图片/ 下的原始文件，不覆盖、不改名。
  - 输出永远是 public/assets/v8/<slot>.jpg（JPEG q80 起步，超体积就降档）。
  - 已经压过的成品不会二次压缩（脚本只读素材库）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "assets" / "真实项目图片"
OUT = ROOT / "public" / "assets" / "v8"

# slot, 源文件（相对素材库）, 目标宽高, 体积上限 KB
SLOTS: list[tuple[str, str, tuple[int, int], int]] = [
    # ⚠️ 源图只允许出自「优质素材/」（用户 2026-11-19 指定）。其它目录的图一律不接。
    # 首屏：风电叶片山路运输（现场 + 护送 + 道路保障）
    ("hero-blade-convoy", "优质素材/web-blade-06-convoy-mountain.png", (1600, 1067), 320),
    # 设备资源（3 张，3:2）
    ("fleet-nacelle", "优质素材/web-nacelle-01-nacelle-lifted-onto-red-trailer.png", (1400, 933), 260),
    ("fleet-blade", "优质素材/web-blade-01-blades-loaded-in-yard.png", (1400, 933), 260),
    ("fleet-lowbed", "优质素材/web-red-02-multi-axle-empty-yard-side.jpg", (1400, 933), 260),
    # 代表项目（3 张，3:2）
    ("project-hanoi", "优质素材/rail-06-hanoi-elevated-piers.jpg", (1400, 933), 260),
    ("project-hcmc", "优质素材/rail-08-hcmc-ben-thanh-station.jpg", (1400, 933), 260),
    ("project-wind", "优质素材/web-blade-04-blade-closeup-day.jpg", (1400, 933), 260),
    # 关于（21:9 满幅：越南 QL1 干线转运）/ 联系（21:9：多轴低平板载变压器）
    ("about-wide", "优质素材/real-02-crawler-rigs-ql1-vietnam.jpg", (2000, 857), 320),
    ("about-team", "优质素材/web-blade-08-team-with-blades.jpg", (1400, 933), 260),
    ("contact-lowbed", "优质素材/web-red-05-lowbed-with-tank.jpg", (2000, 857), 320),
    # 业务页 / 贸易段
    ("services-transformer", "优质素材/real-03-transformer-loaded-red-trailer.jpg", (1600, 686), 280),
    ("trade-port", "优质素材/web-port-03-container-ship.jpg", (1200, 800), 220),
    ("trade-rail", "优质素材/rail-07-hanoi-station-excavation.jpg", (1200, 800), 220),
]


def fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理名字以此开头的 slot")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for slot, rel, size, limit_kb in SLOTS:
        if args.only and not slot.startswith(args.only):
            continue
        src = SRC / rel
        if not src.exists():
            print(f"  X 缺源图：{rel}")
            failures.append(slot)
            continue
        img = Image.open(src)
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

        tiny = img.width < size[0] or img.height < size[1]
        out = fit(img, size)
        target = OUT / f"{slot}.jpg"
        note = ""
        if tiny:
            note = f"  ! 源图 {img.width}x{img.height} 小于目标，已放大"
        if args.dry_run:
            print(f"  {slot:22} {img.width}x{img.height} -> {size[0]}x{size[1]}{note}")
            continue

        q = 80
        while q >= 60:
            out.save(target, "JPEG", quality=q, optimize=True, progressive=True)
            if target.stat().st_size <= limit_kb * 1024:
                break
            q -= 5
        kb = target.stat().st_size / 1024
        flag = "OK " if kb <= limit_kb else "BIG"
        print(f"  {flag} {slot:22} {img.width}x{img.height} -> {size[0]}x{size[1]}  {kb:5.0f} KB (q{q}){note}")

    if failures and not args.dry_run:
        print("\n失败：", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
