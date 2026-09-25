"""网关安全门禁验证：密钥、端点白名单、限流、以及「用最小数据目录能不能真算出结果」。
用法： python probe-engine-gateway.py [gateway_base] [key]
"""
import json, subprocess, sys

GW = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18001"
KEY = sys.argv[2] if len(sys.argv) > 2 else "test-key-abc123"

def curl(args, body=None):
    p = subprocess.run(["curl", "-s", "-m", "60"] + args + ["-w", "\n%{http_code}"],
                       input=(json.dumps(body).encode() if body is not None else None), capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    body_txt, _, code = out.rpartition("\n")
    return int(code or 0), body_txt.strip()[:200]

fail = []
def expect(label, got, want, extra=""):
    ok = got == want
    if not ok: fail.append(f"{label}: 得到 {got}，期望 {want} {extra}")
    print(f"  {'✓' if ok else '✗'} {label} → HTTP {got}{'' if ok else f'（期望 {want}）'} {extra}")

print("=== 1) 端点白名单（引擎能力面不暴露）===")
expect("POST /api/v1/vehicles（车型库后台）", curl(["-X", "POST", f"{GW}/api/v1/vehicles", "-H", f"X-API-Key: {KEY}"])[0], 404)
expect("GET /api/v1/vehicles（车型库）", curl([f"{GW}/api/v1/vehicles"])[0], 404)
expect("GET /api/v1/rates/current（费率）", curl([f"{GW}/api/v1/rates/current", "-H", f"X-API-Key: {KEY}"])[0], 404)
expect("POST /api/v1/border/ddp-costs（口岸费用）", curl(["-X", "POST", f"{GW}/api/v1/border/ddp-costs", "-H", f"X-API-Key: {KEY}"])[0], 404)
expect("POST /api/v1/quote/export（报价单导出）", curl(["-X", "POST", f"{GW}/api/v1/quote/export", "-H", f"X-API-Key: {KEY}"])[0], 404)
expect("POST /api/v1/ai/chat（AI 代理）", curl(["-X", "POST", f"{GW}/api/v1/ai/chat", "-H", f"X-API-Key: {KEY}"])[0], 404)
expect("GET /docs（接口文档）", curl([f"{GW}/docs"])[0], 404)
expect("GET /openapi.json", curl([f"{GW}/openapi.json"])[0], 404)

print("\n=== 2) 密钥门禁 ===")
expect("健康端点免密钥（Render 探活）", curl([f"{GW}/health"])[0], 200)
expect("网关健康端点", curl([f"{GW}/gateway/health"])[0], 200)
expect("route/cost 无密钥", curl(["-X", "POST", f"{GW}/api/v1/route/cost", "--data-binary", "@-"], body={})[0], 401)
expect("route/cost 错密钥", curl(["-X", "POST", f"{GW}/api/v1/route/cost", "-H", "X-API-Key: wrong", "--data-binary", "@-"], body={})[0], 401)

print("\n=== 3) 正确密钥 + 最小数据目录 → 真能算出结果 ===")
st, txt = curl(["-X", "POST", f"{GW}/api/v1/route/cost", "-H", f"X-API-Key: {KEY}",
                "-H", "Content-Type: application/json", "--data-binary", "@-"], body={
    "route": {"origin": {"lat": 31.2304, "lng": 121.4737},
              "destination": {"lat": 21.0278, "lng": 105.8342},
              "border": {"lat": 21.9755, "lng": 106.7089}},
    "cargo": {"weight_kg": 20000, "volume_m3": 60, "type": "normal"},
    "vehicle": {"loading_mode": "full_truck", "vehicle_model_id": "flatbed_13m"},
})
print(f"  HTTP {st}")
if st == 200:
    d = json.loads(txt if txt.startswith("{") else "{}") if False else None
    st2, full = curl(["-X", "POST", f"{GW}/api/v1/route/cost", "-H", f"X-API-Key: {KEY}",
                      "-H", "Content-Type: application/json", "--data-binary", "@-"], body={
        "route": {"origin": {"lat": 31.2304, "lng": 121.4737},
                  "destination": {"lat": 21.0278, "lng": 105.8342}},
        "cargo": {"weight_kg": 20000}, "vehicle": {"loading_mode": "full_truck", "vehicle_model_id": "flatbed_13m"}})
    print(f"  第二次（不带口岸）HTTP {st2}")
    print(f"  ✓ 网关+最小数据目录可用")
else:
    fail.append(f"最小数据目录下测算失败：HTTP {st} {txt}")
    print("  ✗ 见下：", txt[:200])

print("\n" + ("全部通过 ✅" if not fail else "存在问题：\n  - " + "\n  - ".join(fail)))
sys.exit(1 if fail else 0)
