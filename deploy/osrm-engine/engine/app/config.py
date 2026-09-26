"""应用配置（Pydantic BaseSettings，DEVELOPMENT_GOALS.md §4）。

从环境变量 / .env 文件加载，字段自动映射（例如 DEEPSEEK_API_KEY）。
未设置的环境变量使用默认值；类型错误在启动时报错。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── OSRM ──
    # 默认使用公共 OSRM 服务器（免费，~1 req/s，适合询价场景）。
    # 生产环境自建 OSRM 时通过 OSRM_BASE_URL 环境变量覆盖。
    osrm_base_url: str = "https://router.project-osrm.org"
    # 当前本地 OSRM 数据只按默认 car profile 编译，truck profile 待办（§5.2 / §11）。
    # 这也是「未指定车型」以及「车型 profile 兑现不了」时的**回退 profile**。
    osrm_profile: str = "driving"

    # 🆕 v015.4：本机 OSRM **实际编译/提供**的 profile 清单（逗号分隔，全部小写）。
    #
    # 为什么必须有这个声明，而不是只看 HTTP 状态码：
    #   2026-09-23 实测 https://router.project-osrm.org，同一组坐标 河内→胡志明：
    #     /route/v1/driving/... → HTTP 200, distance 1487265.1
    #     /route/v1/truck/...   → HTTP 200, distance 1487265.1   ← 与 driving **逐位相同**
    #     /route/v1/foo/...     → HTTP 200, distance 1487265.1   ← 连不存在的 profile 也是 200
    #   即：公共 demo 对任意 profile 字串都静默按 car 路网返回。把「HTTP 200」当成
    #   「truck 限高限重已生效」就是在骗用户 —— 报价会漏掉限行/限高导致的绕行成本。
    #   所以车型 profile 是否可兑现，由本声明 + 服务端错误码共同判定；
    #   未声明的 profile 一律标注 profile_honored=false（见 services/osrm_client.py）。
    #
    # 自建 truck 路网（osrm-extract -p profile.lua; osrm-routed）后：
    #   OSRM_AVAILABLE_PROFILES=driving,truck   → 路线才按车型限高限重选路。
    osrm_available_profiles: str = "driving"

    # ── 成本预设（附录A） ──
    default_fuel_price_vnd: float = 23320.0   # Petrolimex DO 0,05S-II Vùng 1 2026-07-16
    default_wage_hourly_vnd: float = 180000.0  # 附录A：月薪 ÷ 22天 ÷ 8小时
    loading_rate_vnd_per_ton: float = 50000.0  # §6.3.4
    insurance_rate: float = 0.003              # §6.3.4：货值 × 0.3%
    margin_rate: float = 0.15                  # 售价 = 成本 × (1 + margin_rate)；内部=成本+利润

    # ── DeepSeek AI ──
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"  # DeepSeek V4 Flash（官方 API 模型名）
    deepseek_max_tokens: int = 4096
    deepseek_temperature: float = 0.0      # 分析任务用 0 保证一致性
    deepseek_chat_temperature: float = 0.3  # 对话聊天用稍高的温度


settings = Settings()
