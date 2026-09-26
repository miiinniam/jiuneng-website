"""集中式资源目录解析（桌面版/原生/Docker 通用）。

桌面版（Electron）由主进程通过环境变量 `OSRM_RESOURCE_DIR` 指向用户数据目录，
该目录内含 `data/`（exchange_rate.json / fixed_fees.json / hs_tariff_2026.json / osrm_plus.db）
与 `车辆型号库.csv` —— 这样数据既可持久化，又不随 exe 每次解压丢失。

解析优先级：
1. `OSRM_RESOURCE_DIR`（Electron 设置的用户数据目录，可写持久化）
2. PyInstaller 冻结时与 exe 同级的 `resources/`（打包自带只读默认值兜底）
3. 原生运行回落 backend/ 根（开发态）

本文件为纯 ASCII 模块名，避免打包/导入层面的非 ASCII 模块名风险。
"""
import os
import sys
from pathlib import Path

_ENV_KEY = "OSRM_RESOURCE_DIR"


def resource_dir() -> Path:
    """返回资源根目录。"""
    env = os.environ.get(_ENV_KEY)
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        # PyInstaller：exe 同级 `resources/`（打包时随 extraResources 带入）
        exe_dir = Path(sys.executable).resolve().parent
        sibling = exe_dir / "resources"
        if sibling.exists():
            return sibling
    # 开发态：backend/ 根（_paths.py 位于 backend/app/services/，parents[2] == backend/）
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """资源根下的 `data/` 子目录（汇率/税费/HS 税则/轻量 DB）。"""
    return resource_dir() / "data"


def vehicle_csv_path() -> Path:
    """资源根下的车辆型号库 CSV 路径。"""
    return resource_dir() / "车辆型号库.csv"
