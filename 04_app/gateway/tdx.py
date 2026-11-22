"""TDX (Transport Data eXchange, MOTC Taiwan) EV-charging data: download, normalize, cache.

Credentials: ../../secrets/tdx.env with TDX_CLIENT_ID / TDX_CLIENT_SECRET (never sent to the browser).
Cache:       cache/tdx_stations.json (all city stations + freeway service areas), refreshed every 3 days
             (22 API calls per refresh, well inside the free member quota of ~3,000 calls/month).

Run directly to refresh the cache:  python tdx.py
"""
import json
import os
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
SECRETS = HERE.parent.parent / "secrets" / "tdx.env"
CACHE = HERE / "cache" / "tdx_stations.json"
PART_DIR = HERE / "cache" / "tdx_parts"
TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
API = "https://tdx.transportdata.tw/api/basic/v1/EV"
CITIES = {
    "Taipei": "台北市", "NewTaipei": "新北市", "Taoyuan": "桃園市", "Taichung": "台中市", "Tainan": "台南市",
    "Kaohsiung": "高雄市", "Keelung": "基隆市", "Hsinchu": "新竹市", "HsinchuCounty": "新竹縣",
    "MiaoliCounty": "苗栗縣", "ChanghuaCounty": "彰化縣", "NantouCounty": "南投縣", "YunlinCounty": "雲林縣",
    "ChiayiCounty": "嘉義縣", "Chiayi": "嘉義市", "PingtungCounty": "屏東縣", "YilanCounty": "宜蘭縣",
    "HualienCounty": "花蓮縣", "TaitungCounty": "台東縣", "KinmenCounty": "金門縣", "PenghuCounty": "澎湖縣",
}
SHOP_WORDS = ["家樂福", "全聯", "好市多", "Costco", "COSTCO", "IKEA", "大潤發", "愛買", "百貨", "購物中心", "商場",
              "Mall", "MALL", "outlet", "Outlet", "OUTLET", "三井", "遠百", "新光三越", "SOGO", "量販", "超市", "LaLaport"]


def credentials():
    if not SECRETS.exists():
        return None
    env = dict(line.split("=", 1) for line in SECRETS.read_text().splitlines() if "=" in line)
    cid, secret = env.get("TDX_CLIENT_ID", "").strip(), env.get("TDX_CLIENT_SECRET", "").strip()
    return (cid, secret) if cid and secret else None


def token(client: httpx.Client, cid: str, secret: str) -> str:
    r = client.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
                    headers={"content-type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json()["access_token"]


def zh(value):
    """TDX names are objects like {"Zh_tw": "...", "En": "..."}; fall back to plain strings."""
    if isinstance(value, dict):
        return value.get("Zh_tw") or value.get("En") or ""
    return value or ""


# TDX codes (swagger): Type 1 CCS1, 2 CCS2, 3 CHAdeMO, 4 Tesla TPC, 5 J1772 (Type 1), 6 Mennekes (Type 2),
# 254 others, 255 unknown.  Power is the output mode: 1 = AC, 2 = DC (not kW).
TYPE_NAMES = {1: "CCS1", 2: "CCS2", 3: "CHAdeMO", 4: "Tesla TPC", 5: "J1772", 6: "Type 2", 254: "其他", 255: "未知"}


def derive(item: dict) -> dict:
    """bZ4X (Taiwan) charges with CCS1 on DC and SAE J1772 on AC, so only those connectors count."""
    conns = item.get("connectors") or []
    dc = sum(int(c.get("qty") or 1) for c in conns if c.get("type") == 1 and c.get("power") == 2)
    ac = sum(int(c.get("qty") or 1) for c in conns if c.get("type") == 5 and c.get("power") == 1)
    item.update(bz4x_dc=dc, bz4x_ac=ac, fast=dc > 0, compatible=(dc + ac) > 0, max_kw=None)
    item["summary"] = "、".join(f"{TYPE_NAMES.get(c.get('type'), '未知')} {'快充' if c.get('power') == 2 else '慢充'} ×{c.get('qty') or 1}"
                               for c in conns) or "規格未提供"
    return item


def normalize(raw: dict, city_zh: str, kind: str) -> dict:
    conns = [{"type": c.get("Type"), "power": c.get("Power"), "qty": c.get("Quantity")} for c in (raw.get("Connectors") or [])]
    max_kw = None
    name = zh(raw.get("StationName"))
    loc = raw.get("Location") or {}
    address = zh(loc.get("Address")) if isinstance(loc, dict) else ""
    return {
        "id": raw.get("StationID"),
        "name": name,
        "city": city_zh,
        "kind": kind,  # city | freeway
        "lat": raw.get("PositionLat"),
        "lon": raw.get("PositionLon"),
        "address": address,
        "connectors": conns,
        "max_kw": max_kw,
        "shopping": any(w in name for w in SHOP_WORDS),
        "service_time": zh(raw.get("ServiceTime")) if not isinstance(raw.get("ServiceTime"), list) else "",
        "charging_rate": zh(raw.get("ChargingRate")) if not isinstance(raw.get("ChargingRate"), list) else "",
    } | {}


def fetch_all(verbose=True, max_age_hours=72) -> dict:
    creds = credentials()
    if not creds:
        raise RuntimeError("TDX credentials missing in secrets/tdx.env")
    stations = []
    with httpx.Client(timeout=60) as client:
        auth = {"authorization": f"Bearer {token(client, *creds)}", "accept-encoding": "gzip"}

        def get(path):
            for attempt in range(5):
                r = client.get(f"{API}{path}", params={"$format": "JSON"}, headers=auth)
                if r.status_code == 429:  # free tier is rate limited: wait and retry
                    wait = 30 * (attempt + 1)
                    if verbose:
                        print(f"  429 rate limit, waiting {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            r.raise_for_status()

        # each part is saved as soon as it arrives, so a failure never re-spends quota on parts already fetched
        parts = [(f"/Station/City/{code}", city_zh, "city", code) for code, city_zh in CITIES.items()]
        parts.append(("/Station/Freeway/ServiceArea", "高速公路", "freeway", "Freeway"))
        PART_DIR.mkdir(parents=True, exist_ok=True)
        for path, label, kind, code in parts:
            f = PART_DIR / f"{code}.json"
            if f.exists() and (time.time() - f.stat().st_mtime) < max_age_hours * 3600:
                got = json.loads(f.read_text())
            else:
                data = get(path)
                got = [normalize(s, label, kind) for s in data.get("Stations", [])]
                f.write_text(json.dumps(got, ensure_ascii=False))
                time.sleep(12)  # stay under the per-minute limit
            stations += [derive(x) for x in got]
            if verbose:
                print(f"{label}: {len(got)}", flush=True)
    stations = [s for s in stations if isinstance(s["lat"], (int, float)) and isinstance(s["lon"], (int, float))]
    out = {"updated": time.strftime("%Y-%m-%d %H:%M"), "source": "TDX 運輸資料流通服務（交通部）", "stations": stations}
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out, ensure_ascii=False))
    return out


def load_cache(max_age_hours=72):
    if not CACHE.exists():
        return None, True
    data = json.loads(CACHE.read_text())
    stale = (time.time() - CACHE.stat().st_mtime) > max_age_hours * 3600
    return data, stale


if __name__ == "__main__":
    out = fetch_all()
    s = out["stations"]
    print(f"total {len(s)} | bZ4X-compatible {sum(x['compatible'] for x in s)} | CCS1 fast {sum(x['fast'] for x in s)} "
          f"| shopping {sum(x['shopping'] for x in s)} | freeway fast {sum(x['fast'] for x in s if x['kind'] == 'freeway')}")
