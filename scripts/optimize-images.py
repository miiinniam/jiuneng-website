#!/usr/bin/env python
"""
图片落库工具 —— 把新照片压成站点规格并放进 public/assets/。

为什么需要它：
  站点图片管线是「JPEG quality 80 + optimize」（见 DEVELOPMENT.md §9.1），
  但那次转换是一次性脚本，新照片容易漏压 —— 直接把 2 MB 的 PNG 丢进
  public/assets/ 会让首页变慢，而且 PNG 格式会让 Logo 之外的图白占 10 倍体积。

用法：
    # 单张（自动按用途裁切/缩放到规格，输出到 public/assets/）
    python scripts/optimize-images.py 新截图.png --as system-overview

    # 批量：把 --out 指定为新文件名
    python scripts/optimize-images.py photo1.png photo2.png --out custom-name

    # 只预览不写盘
    python scripts/optimize-images.py 新截图.png --as system-overview --dry-run

规格（详见 IMAGE-SPEC.md）：
    system-overview / system-tracking   1750x1000 (1.75:1)  ≤ 320 KB
    card                                1680x1120 (1.5:1)   ≤ 300 KB
    solution                            1680x1292 (1.3:1)   ≤ 300 KB
    hero                                2000x1200 (5:3)     ≤ 350 KB

⚠️ Logo 类文件（logo-*.png / favicon*.png / apple-touch-icon.png）不需要处理，
   它们必须有透明通道，转 JPEG 会出现白底方块。本脚本会直接拒收。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "public" / "assets"

# 名称 → (宽, 高, 体积上限 KB)
SPECS = {
    "system-overview": (1750, 1000, 320),
    "system-tracking": (1750, 1000, 320),
    "card": (1680, 1120, 300),
    "solution": (1680, 1292, 300),
    "hero": (2000, 1200, 350),
}

LOGO_PATTERNS = ("logo-", "favicon", "apple-touch-icon")


def fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """等比缩放后居中裁切到目标尺寸（cover 语义，和 CSS object-fit: cover 一致）。"""
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def convert(src: Path, target: Path, size: tuple[int, int], limit_kb: int, dry: bool) -> None:
    img = Image.open(src)
    if img.mode in ("RGBA", "P", "LA"):
        # 非 Logo 图不需要透明通道；用白底合成，避免透明区域变成黑边
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    out = fit(img, size)

    quality = 80
    if not dry:
        # 体积超标时逐档降质量，保证不超上限（照片观感差异小于 80→72）
        while quality >= 60:
            out.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
            if target.stat().st_size <= limit_kb * 1024:
                break
            quality -= 5
    shown = target.stat().st_size / 1024 if (not dry and target.exists()) else 0
    print(
        f"  {src.name}  {img.width}x{img.height} → {size[0]}x{size[1]}  "
        f"{'[dry-run]' if dry else f'{shown:.0f} KB (q{quality})'}  → {target.name}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="把新照片压成站点规格并落库到 public/assets/")
    ap.add_argument("files", nargs="+", help="源图片路径")
    ap.add_argument("--as", dest="as_spec", choices=sorted(SPECS), help="按用途套用规格")
    ap.add_argument("--out", help="输出文件名（不含 .jpg）；批量时表示前缀")
    ap.add_argument("--dry-run", action="store_true", help="只打印结果，不写盘")
    args = ap.parse_args()

    if not args.as_spec:
        print("必须指定 --as（用途规格）：", ", ".join(sorted(SPECS)))
        return 2

    for f in args.files:
        src = Path(f)
        if not src.exists():
            src = ROOT / f
        if not src.exists():
            print(f"  ✗ 找不到文件：{f}")
            return 1
        if any(src.name.startswith(p) for p in LOGO_PATTERNS):
            print(f"  ✗ {src.name} 属于 Logo/图标类，必须保持 PNG 透明通道，不要走本脚本")
            return 1
        name = args.out if args.out else src.stem
        if len(args.files) > 1 and args.out:
            name = f"{args.out}-{src.stem}"
        convert(src, ASSETS / f"{name}.jpg", SPECS[args.as_spec][:2], SPECS[args.as_spec][2], args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
