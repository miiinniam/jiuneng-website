"""货物类型预设参数（DEVELOPMENT_GOALS.md §4.4）。

车辆型号相关的预设已经迁移到 `vehicle_registry.py`（读取
`OSRM++/车辆型号库/车辆型号库.csv`，具体型号由用户手工维护，不再是这里的代码常量）。

TODO: 目前是代码里的常量表，对应文档 §7 的 cargo_type_rates 表；
等接入数据库后应改为从 DB 读取，让管理界面可增删改。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CargoTypeRate:
    rate_multiplier: float
    fuel_penalty: float = 0.0


CARGO_TYPE_RATES: dict[str, CargoTypeRate] = {
    "normal": CargoTypeRate(rate_multiplier=1.0),
    "cold_chain": CargoTypeRate(rate_multiplier=1.3, fuel_penalty=0.20),
    "hazardous": CargoTypeRate(rate_multiplier=1.5),
    "oversized": CargoTypeRate(rate_multiplier=1.4),
    "heavy_equipment": CargoTypeRate(rate_multiplier=1.5),
    "other": CargoTypeRate(rate_multiplier=1.0),
}


# ── 货物类型进出口费用快速估算（非 HS 码精确查询）──

@dataclass(frozen=True)
class CargoImportExportEstimate:
    """根据货物类型的粗略进出口费用估算，用于不需要 HS 码的快速报价场景。"""
    export_fee_rmb_per_vehicle: float   # 每车出口费用 (¥)
    import_fee_rmb_per_vehicle: float   # 每车进口费用 (¥)
    estimated_duty_rate: float          # 预估关税率
    estimated_vat_rate: float           # 预估增值税率
    description_zh: str                 # 中文说明
    description_vi: str                 # 越南语说明


CARGO_IMPORT_EXPORT_ESTIMATES: dict[str, CargoImportExportEstimate] = {
    "normal": CargoImportExportEstimate(
        export_fee_rmb_per_vehicle=800,
        import_fee_rmb_per_vehicle=1500,
        estimated_duty_rate=0.05,
        estimated_vat_rate=0.10,
        description_zh="普通货物：出口报关+口岸操作 ~800¥/车，进口清关 ~1500¥/车",
        description_vi="Hàng thông thường: thông quan XK ~800¥/xe, NK ~1500¥/xe",
    ),
    "oversized": CargoImportExportEstimate(
        export_fee_rmb_per_vehicle=1500,
        import_fee_rmb_per_vehicle=3000,
        estimated_duty_rate=0.08,
        estimated_vat_rate=0.10,
        description_zh="超限货物：出口报关+超限申报 ~1500¥/车，进口清关+检验 ~3000¥/车",
        description_vi="Hàng quá khổ: thông quan XK ~1500¥/xe, NK ~3000¥/xe",
    ),
    "heavy_equipment": CargoImportExportEstimate(
        export_fee_rmb_per_vehicle=2000,
        import_fee_rmb_per_vehicle=5000,
        estimated_duty_rate=0.08,
        estimated_vat_rate=0.10,
        description_zh="重型设备：出口报关+特种装卸 ~2000¥/车，进口清关+检验 ~5000¥/车",
        description_vi="Thiết bị nặng: thông quan XK ~2000¥/xe, NK ~5000¥/xe",
    ),
    "cold_chain": CargoImportExportEstimate(
        export_fee_rmb_per_vehicle=1200,
        import_fee_rmb_per_vehicle=2500,
        estimated_duty_rate=0.05,
        estimated_vat_rate=0.10,
        description_zh="冷链货物：出口报关+温控 ~1200¥/车，进口清关+检验 ~2500¥/车",
        description_vi="Hàng lạnh: thông quan XK ~1200¥/xe, NK ~2500¥/xe",
    ),
    "hazardous": CargoImportExportEstimate(
        export_fee_rmb_per_vehicle=2000,
        import_fee_rmb_per_vehicle=4000,
        estimated_duty_rate=0.05,
        estimated_vat_rate=0.10,
        description_zh="危险品：出口报关+危品申报 ~2000¥/车，进口清关+检验 ~4000¥/车",
        description_vi="Hàng nguy hiểm: thông quan XK ~2000¥/xe, NK ~4000¥/xe",
    ),
    "other": CargoImportExportEstimate(
        export_fee_rmb_per_vehicle=800,
        import_fee_rmb_per_vehicle=1500,
        estimated_duty_rate=0.05,
        estimated_vat_rate=0.10,
        description_zh="其他货物：标准进出口费用",
        description_vi="Hàng khác: phí XNK tiêu chuẩn",
    ),
}
