#!/usr/bin/env python
"""把「优质素材」34 张照片 + 3 段视频落成 v9 站点图位。

与 build-photo-slots.py 的分工：
  - 那个脚本管 v8 的首页/业务/关于图位（固定 17 个槽位）；
  - 这个脚本管 v9 项目页 7 个分类（主图 + 缩略图）与「作业实录」视频。

规则：
  - 源图永远只读（public/assets/真实项目图片/），不覆盖、不改名；
  - 产物只写 public/assets/v9/，可反复重跑；
  - 一张表管全部对位：换图只改 src 一列。

用法：
    env -u PYTHONPATH python scripts/build-photo-v9.py            # 全部
    env -u PYTHONPATH python scripts/build-photo-v9.py --dry-run
    env -u PYTHONPATH python scripts/build-photo-v9.py --only cat-blade
    env -u PYTHONPATH python scripts/build-photo-v9.py --skip-video
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "public" / "assets" / "真实项目图片"
OUT = ROOT / "public" / "assets" / "v9"

MAIN = (1200, 800)   # 3:2 主图
THUMB = (640, 480)   # 4:3 缩略图

# (输出相对路径, 源图相对素材库, 目标尺寸, 体积上限KB, 裁切锚点)
# 锚点：center / top / bottom / left / right，主体不在正中时用得上。
SLOTS: list[tuple[str, str, tuple[int, int], int, str]] = [
    # 01 风电叶片运输（8）：装车 / 山路 / 护送 / 团队
    ("cat-blade/main.jpg", "优质素材/web-blade-02-blade-on-mountain-road.jpg", MAIN, 240, "center"),
    ("cat-blade/t-01.jpg", "优质素材/web-blade-01-blades-loaded-in-yard.png", THUMB, 120, "center"),
    ("cat-blade/t-02.jpg", "优质素材/web-blade-03-blade-closeup-dusk.png", THUMB, 120, "center"),
    ("cat-blade/t-03.jpg", "优质素材/web-blade-04-blade-closeup-day.jpg", THUMB, 120, "center"),
    ("cat-blade/t-04.jpg", "优质素材/web-blade-05-convoy-valley.jpg", THUMB, 120, "center"),
    ("cat-blade/t-05.jpg", "优质素材/web-blade-06-convoy-mountain.png", THUMB, 120, "center"),
    ("cat-blade/t-06.jpg", "优质素材/web-blade-07-road-widening-loader-portrait.jpg", THUMB, 120, "center"),
    ("cat-blade/t-07.jpg", "优质素材/web-blade-08-team-with-blades.jpg", THUMB, 120, "center"),
    # 02 风机部件吊装（3）：叶片根部对接、双吊装车、机舱上车
    #    tower-02/tower-03 文件名写着「塔筒」，画面其实是叶片根部作业，图示按画面写。
    ("cat-lift/main.jpg", "优质素材/web-tower-02-tower-convoy.png", MAIN, 240, "center"),
    ("cat-lift/t-01.jpg", "优质素材/web-tower-03-tower-section-tandem-lift.png", THUMB, 120, "center"),
    ("cat-lift/t-02.jpg", "优质素材/web-nacelle-01-nacelle-lifted-onto-red-trailer.png", THUMB, 120, "center"),
    # 03 变压器与港口吊装（4）
    ("cat-transformer/main.jpg", "优质素材/real-01-transformer-lashing-in-ship-hold.jpg", MAIN, 240, "center"),
    ("cat-transformer/t-01.jpg", "优质素材/real-02-transformer-port-crane-onto-trailer.jpg", THUMB, 120, "center"),
    ("cat-transformer/t-02.jpg", "优质素材/real-03-transformer-loaded-red-trailer.jpg", THUMB, 120, "center"),
    ("cat-transformer/t-03.jpg", "优质素材/real-04-transformer-floating-crane-night.jpg", THUMB, 120, "center"),
    # 04 工程机械与重卡（7）
    ("cat-machine/main.jpg", "优质素材/real-02-crawler-rigs-ql1-vietnam.jpg", MAIN, 240, "center"),
    ("cat-machine/t-01.jpg", "优质素材/real-01-rotary-rig-night-lowbed.jpg", THUMB, 120, "center"),
    ("cat-machine/t-02.jpg", "优质素材/real-03-rotary-rig-on-blue-lowbed.jpg", THUMB, 120, "center"),
    ("cat-machine/t-03.jpg", "优质素材/web-machine-01-excavator-green-lowbed.jpg", THUMB, 120, "center"),
    ("cat-machine/t-04.jpg", "优质素材/web-machine-02-yard-trucks.jpg", THUMB, 120, "center"),
    ("cat-machine/t-05.jpg", "优质素材/web-machine-03-lowbed-yard.jpg", THUMB, 120, "center"),
    ("cat-machine/t-06.jpg", "优质素材/web-machine-04-heavy-module-to-riverside-barge.jpg", THUMB, 120, "center"),
    # 05 多轴低平板 / 轴线车（5）
    #    red-04 是玖一自有车在场地拉横幅拍的（横幅上有联系人手机与网址），只做缩略图；
    #    主图用 red-05（多轴低平板载变压器，越南场地）。
    ("cat-lowbed/main.jpg", "优质素材/web-red-05-lowbed-with-tank.jpg", MAIN, 240, "center"),
    ("cat-lowbed/t-01.jpg", "优质素材/web-red-01-multi-axle-empty-yard.jpg", THUMB, 120, "center"),
    ("cat-lowbed/t-02.jpg", "优质素材/web-red-02-multi-axle-empty-yard-side.jpg", THUMB, 120, "center"),
    ("cat-lowbed/t-03.jpg", "优质素材/web-red-03-axle-line-closeup.png", THUMB, 120, "center"),
    ("cat-lowbed/t-04.jpg", "优质素材/web-red-04-lowbed-loaded-mountain.png", THUMB, 120, "center"),
    # 06 轨道交通工程（5）：3 张越南 + 2 张欧洲资料图
    ("cat-rail/main.jpg", "优质素材/rail-07-hanoi-station-excavation.jpg", MAIN, 240, "center"),
    ("cat-rail/t-01.jpg", "优质素材/rail-06-hanoi-elevated-piers.jpg", THUMB, 120, "center"),
    ("cat-rail/t-02.jpg", "优质素材/rail-08-hcmc-ben-thanh-station.jpg", THUMB, 120, "center"),
    ("cat-rail/t-03.jpg", "优质素材/rail-01-metro-tbm-tunnel.jpg", THUMB, 120, "center"),
    ("cat-rail/t-04.jpg", "优质素材/rail-02-metro-tbm-launch-shaft.jpg", THUMB, 120, "center"),
    # 07 港口与船舶（2）
    ("cat-port/main.jpg", "优质素材/web-port-03-container-ship.jpg", MAIN, 240, "center"),
    ("cat-port/t-01.jpg", "优质素材/web-port-01-crane-lifting.png", THUMB, 120, "center"),
]

# 作业实录：输出名, 源 mp4, 抽帧秒数, 画面上限
VIDEOS: list[tuple[str, str, float]] = [
    ("loading-drill-rig", "优质素材/3a6546885c51248426fe739084efae6a.mp4", 4.0),
    ("floating-crane-night", "优质素材/44c797c7b1f852a43374fb700428649b.mp4", 3.0),
    ("port-crane-day", "优质素材/d3a051e619f599878299faf9facecbf7.mp4", 3.0),
]


def crop(img: Image.Image, size: tuple[int, int], anchor: str = "center") -> Image.Image:
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    dx = resized.width - tw
    dy = resized.height - th
    left = {"left": 0, "center": dx // 2, "right": dx}.get(anchor, dx // 2)
    top = {"top": 0, "center": dy // 2, "bottom": dy}.get(anchor, dy // 2)
    return resized.crop((left, top, left + tw, top + th))


def save_jpeg(img: Image.Image, target: Path, limit_kb: int) -> tuple[int, int]:
    q = 82
    while q >= 55:
        img.save(target, "JPEG", quality=q, optimize=True, progressive=True)
        if target.stat().st_size <= limit_kb * 1024:
            break
        q -= 4
    return q, int(target.stat().st_size / 1024)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理输出路径以此开头的槽位，如 cat-blade")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-video", action="store_true")
    ap.add_argument("--video-only", action="store_true")
    args = ap.parse_args()

    failures: list[str] = []

    for rel_out, rel_src, size, limit_kb, anchor in SLOTS:
        if args.video_only:
            break
        if args.only and not rel_out.startswith(args.only):
            continue
        src = SRC / rel_src
        if not src.exists():
            print(f"  X 缺源图：{rel_src}")
            failures.append(rel_out)
            continue
        img = Image.open(src)
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

        out = crop(img, size, anchor)
        target = OUT / rel_out
        if args.dry_run:
            print(f"  {rel_out:26} {img.width}x{img.height} -> {size[0]}x{size[1]} ({anchor})")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        q, kb = save_jpeg(out, target, limit_kb)
        flag = "OK " if kb <= limit_kb else "BIG"
        print(f"  {flag} {rel_out:26} {img.width}x{img.height} -> {kb:4d} KB (q{q})")

    if not args.skip_video and not args.only:
        out_dir = OUT / "video"
        if not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
        for name, rel_src, at in VIDEOS:
            src = SRC / rel_src
            if not src.exists():
                print(f"  X 缺源视频：{rel_src}")
                failures.append(name)
                continue
            if args.dry_run:
                print(f"  video/{name:22} <- {rel_src} @{at}s")
                continue
            poster = out_dir / f"{name}.jpg"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(src), "-frames:v", "1",
                 "-vf", "scale=1280:-1", "-q:v", "4", str(poster)],
                check=True,
            )
            mp4 = out_dir / f"{name}.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an",
                 "-vf", "scale=1152:-2", "-c:v", "libx264", "-preset", "slow", "-crf", "31",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
                check=True,
            )
            pk = int(poster.stat().st_size / 1024)
            vk = int(mp4.stat().st_size / 1024)
            flag = "OK " if pk <= 200 and vk <= 1536 else "BIG"
            print(f"  {flag} video/{name:22} poster {pk:4d} KB · mp4 {vk:5d} KB")

    if failures and not args.dry_run:
        print("\n失败：", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
