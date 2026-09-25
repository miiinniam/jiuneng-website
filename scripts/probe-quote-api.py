"""官网测算出口 vs 真引擎：验区间算法 + 内部字段零泄漏。

用法（在仓库根目录直接跑，默认指向本机现状）：
    python scripts/probe-quote-api.py
    python scripts/probe-quote-api.py --site http://127.0.0.1:3300 --engine http://127.0.0.1:18000

也可用环境变量覆盖默认值：SITE_URL / ENGINE_URL / PROBE_TIMEOUT / CURL_BIN。

不依赖 requests：本机 python urllib 走 127.0.0.1 会被环境拦截（curl 正常），统一 subprocess 调 curl。
"""
import argparse, json, os, subprocess, sys


def parse_args():
    ap = argparse.ArgumentParser(description="官网 /api/osrm-quote 探针：区间 = 引擎售价 ±10% + 内部字段零泄漏")
    ap.add_argument("--site", default=os.environ.get("SITE_URL", "http://127.0.0.1:3300"),
                    help="官网地址（默认本机 3300，或环境变量 SITE_URL）")
    ap.add_argument("--engine", default=os.environ.get("ENGINE_URL", "http://127.0.0.1:18000"),
                    help="OSRM++ 引擎地址（默认本机 18000，或环境变量 ENGINE_URL）")
    ap.add_argument("--timeout", type=int, default=int(os.environ.get("PROBE_TIMEOUT", "180")),
                    help="单次请求 curl 超时秒数（默认 180，或环境变量 PROBE_TIMEOUT）")
    return ap.parse_args()


ARGS = parse_args()
SITE = ARGS.site.rstrip("/")
ENGINE = ARGS.engine.rstrip("/")
TIMEOUT = ARGS.timeout
CURL = os.environ.get("CURL_BIN", "curl")


def post(url, payload, timeout=None):
    """统一走 curl（本机 python urllib 直连 127.0.0.1 会被环境拦截）。"""
    p = subprocess.run(
        [CURL, "-s", "-m", str(timeout or TIMEOUT), "-X", "POST", url,
         "-H", "Content-Type: application/json", "--data-binary", "@-",
         "-w", "\n%{http_code}"],
        input=json.dumps(payload).encode(), capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    body, _, code = out.rpartition("\n")
    try:
        return int(code or 0), json.loads(body)
    except Exception:
        return int(code or 0), body[:300]


print(f"官网 = {SITE}\n引擎 = {ENGINE}")

# 引擎侧原始数值（用来核对区间算法）
st, raw = post(f"{ENGINE}/api/v1/route/cost", {
    "route": {"origin": {"lat": 31.2304, "lng": 121.4737},
              "destination": {"lat": 21.0278, "lng": 105.8342},
              "border": {"lat": 21.9755, "lng": 106.7089}},
    "cargo": {"weight_kg": 20000, "volume_m3": 60, "type": "normal"},
    "vehicle": {"loading_mode": "full_truck", "vehicle_model_id": "flatbed_13m"},
})
print(f"引擎直连 HTTP {st}")
if st != 200:
    print("引擎没起来或报错：", raw)
    print(f"提示：先按 DEVELOPMENT.md §14.7 把引擎跑到 {ENGINE}（或 --engine 指向别处）")
    sys.exit(1)
sell = raw["price_vnd"]
expect_min = round(sell * 0.9 / 100000) * 100000
expect_max = round(sell * 1.1 / 100000) * 100000
print(f"  引擎售价 = {sell:,.0f} VND → 期望区间 {expect_min:,.0f} – {expect_max:,.0f}")
print(f"  引擎含有的内部字段：{sorted(k for k in raw if k in ('breakdown','profit_vnd','margin_rate','border_fees','timing','suggestions','geometry'))}")

fail = []
LEAK = ("breakdown", "profit_vnd", "margin_rate", "border_fees", "cost_distance", "cost_fuel",
        "cost_toll", "cost_insurance", "cost_loading", "geometry", "coor", "secret")


def check_leak(label, obj):
    blob = json.dumps(obj, ensure_ascii=False)
    hits = [k for k in LEAK if k in blob]
    if hits:
        fail.append(f"{label}: 泄漏字段 {hits}")
        print(f"  ✗ {label} 泄漏：{hits}")
    else:
        print(f"  ✓ {label}：内部字段零泄漏")


# ① 整车 13 米
st, site = post(f"{SITE}/api/osrm-quote", {
    "origin": "上海", "destination": "河内", "border": "友谊关口岸",
    "weight_kg": 20000, "volume_m3": 60, "mode": "full_truck", "vehicle_model_id": "flatbed_13m"})
print(f"\n① 整车 13 米 上海→河内（经友谊关口岸） HTTP {st}")
print("  响应：", json.dumps(site, ensure_ascii=False)[:400])
if st != 200 or not site.get("ok"):
    fail.append(f"整车请求失败: {site}")
else:
    if (site["price_min_vnd"], site["price_max_vnd"]) != (expect_min, expect_max):
        fail.append(f"区间不符：拿到 {site['price_min_vnd']}/{site['price_max_vnd']}，期望 {expect_min}/{expect_max}")
    else:
        print(f"  ✓ 区间 = 售价 ±10% 取整到 10 万（{site['price_min_vnd']:,} – {site['price_max_vnd']:,}）")
    for k, want in (("origin", "上海"), ("destination", "河内"), ("border", "友谊关口岸"), ("vehicle_label", "普通平板 13 米")):
        got = site.get(k)
        got = got.get("label") if isinstance(got, dict) else got
        if got != want: fail.append(f"{k} 应为 {want}，实际 {got}")
    print(f"  ✓ 里程 {site['distance_km']} km / 预计行驶 {site['driving_h']} h / {site['vehicle_count']} 车 / {site['vehicle_label']}")
    check_leak("整车响应", site)

# ② 拼车（不给车型）
st, site2 = post(f"{SITE}/api/osrm-quote", {
    "origin": "深圳", "destination": "河内", "weight_kg": 8000, "volume_m3": 25})
print(f"\n② 拼车 深圳→河内（8 吨 / 25 m³） HTTP {st}")
if st == 200 and site2.get("ok"):
    print(f"  ✓ 里程 {site2['distance_km']} km / {site2['vehicle_count']} 车 / 区间 {site2['price_min_vnd']:,} – {site2['price_max_vnd']:,} VND")
    check_leak("拼车响应", site2)
else:
    fail.append(f"拼车请求失败: {site2}")

# ③ 非法输入（不猜坐标、不猜货重）
for label, body, want in [
    ("未知城市", {"origin": "火星", "destination": "河内", "weight_kg": 1000}, "unknown_origin"),
    ("缺货重", {"origin": "上海", "destination": "河内", "weight_kg": 0}, "bad_weight"),
    ("整车没给车型", {"origin": "上海", "destination": "河内", "weight_kg": 1000, "mode": "full_truck"}, "bad_vehicle"),
]:
    st, r = post(f"{SITE}/api/osrm-quote", body)
    ok = (st == 200 and r.get("ok") is False and r.get("reason") == want)
    print(f"\n③ {label} → {'✓' if ok else '✗'} reason={r.get('reason')} note={str(r.get('note'))[:40]}")
    if not ok: fail.append(f"{label} 期望 {want}，实际 {r}")

print("\n" + ("全部通过 ✅" if not fail else "存在问题：\n  - " + "\n  - ".join(fail)))
sys.exit(1 if fail else 0)
