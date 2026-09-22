#!/usr/bin/env python
"""
生成社交分享图 public/assets/og-image.png（1200x630）。

v0.6 明亮版：原图是深蓝底品牌卡（平均亮度 37/255），与浅色化后的站点
观感不一致，这里按同一套设计令牌重做一版浅色卡。

改文案就改下面的 COPY，然后重跑：
    python scripts/make-og-image.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "assets" / "og-image.png"
LOGO = ROOT / "public" / "assets" / "logo-horizontal.png"

W, H = 1200, 630
NAVY = (0, 16, 48)
BLUE = (0, 64, 192)
CYAN = (32, 128, 248)
MUTED = (74, 91, 115)
BG = (248, 251, 255)
BG2 = (232, 240, 251)

# 文案全部取自站点真实内容（index.html / main.tsx），不要在这里新造事实
COPY = {
    "title": "面向中国企业的工程物流平台",
    "sub": "工程物流 · 进出口报关 · 国际贸易",
    "lead": "以数字化系统管理客户询价、方案设计、报价、业务实施与项目交付",
    "foot": "Hanoi, Vietnam   ·   jiuneng.space",
}

FONTS = {
    "light": r"C:\Windows\Fonts\msyhl.ttc",
    "regular": r"C:\Windows\Fonts\msyh.ttc",
    "bold": r"C:\Windows\Fonts\msyhbd.ttc",
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS[kind], size)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 由左上到右下的浅蓝渐变底
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(BG[i] + (BG2[i] - BG[i]) * t) for i in range(3)))

    # 左上角柔和的青色光斑（品牌 accent，不做重暗色）
    glow = Image.new("RGB", (W, H), BG)
    gd = ImageDraw.Draw(glow)
    for r in range(320, 0, -8):
        a = int(26 * (1 - r / 320))
        gd.ellipse([W - 260 - r, -180 - r, W - 260 + r, -180 + r], fill=(32 + 200, 128 + 100, 248))
    img = Image.blend(img, glow, 0.10)
    d = ImageDraw.Draw(img)

    # 官方彩色 Logo（禁止改色/加投影）
    if LOGO.exists():
        logo = Image.open(LOGO).convert("RGBA")
        lh = 58
        logo = logo.resize((round(logo.width * lh / logo.height), lh), Image.LANCZOS)
        img.paste(logo, (80, 74), logo)

    d.text((80, 186), COPY["sub"], font=font("regular", 28), fill=BLUE)
    d.text((80, 234), COPY["title"], font=font("light", 62), fill=NAVY)
    d.text((80, 344), COPY["lead"], font=font("light", 27), fill=MUTED)

    d.line([(80, 452), (W - 80, 452)], fill=(219, 228, 240), width=2)
    d.text((80, 486), COPY["foot"], font=font("regular", 25), fill=MUTED)

    # 品牌渐变条：深蓝 → 品牌蓝 → 信号青（与 Logo 标准包一致）
    for x in range(W):
        t = x / (W - 1)
        if t < 0.5:
            k = t / 0.5
            c = tuple(round(NAVY[i] + (BLUE[i] - NAVY[i]) * k) for i in range(3))
        else:
            k = (t - 0.5) / 0.5
            c = tuple(round(BLUE[i] + (CYAN[i] - BLUE[i]) * k) for i in range(3))
        d.line([(x, H - 10), (x, H)], fill=c)

    img.save(OUT, "PNG", optimize=True)
    print(f"已生成 {OUT}  {img.width}x{img.height}  {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
