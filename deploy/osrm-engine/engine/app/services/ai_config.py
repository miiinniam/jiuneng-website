"""AI 配置持久化：DeepSeek API Key。

前端「设置」弹窗保存 Key 后经 `POST /api/v1/ai/config` 写入此处（`resource_dir()/data/ai_config.json`），
并立即更新 `settings.deepseek_api_key`（运行中生效）；重启后由 main.py lifespan 加载。

⚠️ 只持久化 api_key；model / base_url 属代码级配置，始终由 config.py 默认值决定
  （deepseek_v4_flash + https://api.deepseek.com），**不随文件覆盖**，避免旧文件里的
  "deepseek-chat" 覆盖新默认。且校验：拒绝非 sk- 形态的幽灵值（如 npx .../文件路径），
  否则非法 Key 会被当"已配置"、且 httpx 无法编码非 ASCII Header 导致 /ai/status 500。
"""
import json
import re
from pathlib import Path

from app.config import settings
from app.services._paths import resource_dir

# DeepSeek API Key 形态：sk- 开头，后续无空白的字符串（至少 10 位）
_VALID_KEY = re.compile(r"^sk-\S{10,}$")


def _is_valid_key(key: str) -> bool:
    return bool(key) and bool(_VALID_KEY.match(key.strip()))


def _config_file() -> Path:
    return resource_dir() / "data" / "ai_config.json"


def _mask(key: str) -> str:
    if not key:
        return ""
    return (key[:5] + "••••" + key[-4:]) if len(key) > 9 else "••••"


def get_ai_config() -> dict:
    """返回当前 AI 配置状态（Key 掩码显示）。非法 Key 视同未配置。"""
    key = settings.deepseek_api_key or ""
    if not _is_valid_key(key):
        key = ""
    return {
        "has_key": bool(key),
        "masked_key": _mask(key),
        "model": settings.deepseek_model,      # 始终 config 默认（deepseek-v4-flash）
        "base_url": settings.deepseek_base_url,
    }


def load_ai_config() -> dict | None:
    """启动时仅从文件加载 api_key（模型/地址不覆盖代码默认）。返回已加载配置或 None。"""
    try:
        f = _config_file()
        if not f.exists():
            return None
        cfg = json.loads(f.read_text(encoding="utf-8"))
        if _is_valid_key(str(cfg.get("api_key", ""))):
            settings.deepseek_api_key = str(cfg["api_key"]).strip()
        return cfg
    except Exception:
        return None


def save_ai_config(api_key: str, model: str | None = None, base_url: str | None = None) -> dict:
    """保存 API Key 并立即生效（写文件 + 更新内存 settings）。
    非法 Key（非 sk- 形态）不持久化、不生效，防止污染。model/base_url 忽略（由 config 默认决定）。"""
    api_key = (api_key or "").strip()
    # 仅接受合法 DeepSeek Key；否则视为"未配置"（不写入垃圾值）
    if api_key and not _is_valid_key(api_key):
        settings.deepseek_api_key = ""
        try:
            f = _config_file()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"api_key": ""}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return get_ai_config()

    settings.deepseek_api_key = api_key  # 立即生效（无需重启）
    try:
        f = _config_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"api_key": api_key}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 写文件失败也保持内存生效
    return get_ai_config()
