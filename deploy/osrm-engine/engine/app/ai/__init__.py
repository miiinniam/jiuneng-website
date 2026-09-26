"""能力层（v006）：`spec.py` 声明 + `registry.py` 生成与调度。

加一个 AI 能力只需要两步：
1. 在 `app/ai/spec.py` 的 `SPECS` 里加一条 `CapabilitySpec`；
2. 在 `app/services/ai_tools.py` 里写执行器并 `registry.register_executor(name, fn)`。

tool schema / 系统提示清单 / 权限 / 审计会自动跟上，不需要再同步别处。
"""
