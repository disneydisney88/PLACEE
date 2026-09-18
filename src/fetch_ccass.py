# -*- coding: utf-8 -*-
"""fetch_ccass.py — Phase 2：CCASS 每日持股抓取（webb-database鏡像）

來源與方法：
- webb-database.com 有 JS cookie 挑戰；用瀏覽器（ZCode IAB）過一次，
  抽出 ayuus cookie 存 checkpoints/webb_cookie.txt（連同精確UA）。
- 挑戰偵測：回應含「JS required」或 <2KB → ChallengeError → 停LOW置信行，
  寫 NEED_COOKIE.flag 等人手/瀏覽器更新後續跑（斷點續傳）。
- 交易日曆：用 hk_prices_master.csv 該股日期（同市場同步）。
- 禮貌：全域 1.6s 間隔。

視窗策略（KNOWN_ISSUES #3 有記錄）：
- Tier 1（00254、02113 兩個必過個案）：D-30 .. D+60 全窗
- Tier 2（其餘有具名承配人事件）：D-10 .. D+25 縮窗

輸出：cache/ccass/ccass_daily.csv（append，斷點=已存在code+date組合）
"""
import io
import json
import pathlib
import re
import sys
import time

import pandas as pd
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "ccass"
CACHE.mkdir(parents=True, exist_ok=True)
CKPT = ROOT / "checkpoints"
DAILY_CSV = CACHE / "ccass_daily.csv"
ISSUE_FILE = CKPT / "issue_ids.json"
COOKIE_FILE = CKPT / "webb_cookie.txt"
FLAG_FILE = CKPT / "NEED_COOKIE.flag"
STATE_FILE = CKPT / "ccass_state.json"

BASE = "https://webb-database.com"
MIN_INTERVAL = 1.6

RETAIL_WHITELIST = {
    "B01955": "富途", "B01668": "耀才", "B02159": "盈立", "B02142": "老虎",
    "B02175": "微牛", "B01584": "致富", "B02195": "長橋", "B01345": "輝立",
    "B01590": "盈透", "B01904": "華盛",
}

_last_hit = 0.0


def _sleep_rate():
    global _last_hit
    wait = MIN_INTERVAL - (time.time() - _last_hit)
    if wait > 0:
        time.sleep(wait)
    _last_hit = time.time()


def load_session() -> requests.Session:
    s = requests.Session()
    if COOKIE_FILE.exists():
        txt = COOKIE_FILE.read_text(encoding="utf-8").strip().splitlines()
        s.headers["User-Agent"] = txt[0]
        if len(txt) > 1:
            s.headers["Cookie"] = txt[1]
    else:
        raise SystemExit("缺少 checkpoints/webb_cookie.txt（首兩行=UA、Cookie）")
    return s


class ChallengeError(RuntimeError):
    pass


def _get(s: requests.Session, url: str, timeout: int = 60) -> str:
    delay = 3.0
    last = ""
    for attempt in range(3):
        _sleep_rate()
        try:
            r = s.get(url, timeout=timeout)
            html = r.text
            # 挑戰頁特徵：極短或「JS required」；「有殼冇表」係有效空日
            challenge = ("JS required" in html) or len(html) < 2000
            if r.status_code == 200 and not challenge:
                return html
            last = f"status={r.status_code} len={len(html)}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(delay)
        delay *= 2
    raise ChallengeError(f"挑戰/失敗: {url[:80]} {last}")


def load_issue_ids() -> dict:
    if ISSUE_FILE.exists():
        return json.loads(ISSUE_FILE.read_text(encoding="utf-8"))
    return {}


def save_issue_ids(d: dict):
    ISSUE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")


def get_issue_id(s: requests.Session, code: str) -> str:
    cache = load_issue_ids()
    if code in cache:
        return cache[code]
    html = _get(s, f"{BASE}/dbpub/orgdata.asp?code={code}&Submit=current")
    m = sorted(set(re.findall(r"choldings\.asp\?i=(\d+)", html)),
               key=lambda x: -int(x))
    if not m:
        raise ValueError(f"{code}: orgdata冇issue id")
    cache[code] = m[0]
    save_issue_ids(cache)
    return m[0]


def fetch_day(s: requests.Session, issue_id: str, date_iso: str) -> list[dict]:
    """單日持股快照 → [{participant_id,name,shares,pct}]"""
    html = _get(s, f"{BASE}/ccass/choldings.asp?i={issue_id}&d={date_iso}")
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return []  # 有效「冇數據」頁（殼有但冇表）
    if not tables:
        return []
    big = max(tables, key=len)
    cols = [re.sub(r"\s+", " ", str(c)) for c in big.columns]
    idcol = next((c for c in cols if "CCASS ID" in c), None)
    namecol = next((c for c in cols if c.strip().lower().startswith("name")), None)
    holdcol = next((c for c in cols if "holding" in c.lower()), None)
    stkcol = next((c for c in cols if "stake" in c.lower() and "%" in c), None)
    if not (idcol and holdcol):
        return []
    out = []
    for _, r in big.iterrows():
        pid = str(r[idcol]).strip()
        if not re.match(r"^[BC]\d{5}$", pid):
            continue
        shares = None
        try:
            shares = int(str(r[holdcol]).replace(",", ""))
        except Exception:
            pass
        pct = None
        if stkcol:
            try:
                pct = float(str(r[stkcol]).replace(",", "").replace("%", ""))
            except Exception:
                pass
        out.append({"participant_id": pid,
                    "participant_name": str(r[namecol]).strip() if namecol else "",
                    "shares": shares, "pct": pct})
    return out


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(st: dict):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st), encoding="utf-8")
    tmp.replace(STATE_FILE)


def trading_dates(prices: pd.DataFrame, code: str) -> list:
    g = prices[prices["code"] == code]
    return [d.date() for d in pd.to_datetime(g["date"])]


def window_dates(dates: list, ann, before: int, after: int) -> list:
    past = [d for d in dates if d <= ann][-before:]
    future = [d for d in dates if d > ann][:after]
    return past + future


def append_daily(code: str, date_iso: str, rows: list[dict]):
    new = not DAILY_CSV.exists()
    import csv
    with open(DAILY_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "date", "participant_id",
                                          "participant_name", "shares", "pct"])
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({"code": code, "date": date_iso, **r})


def main():
    tier1 = sys.argv[1] if len(sys.argv) > 1 else "tier1"
    sys.path.insert(0, str(ROOT / "src"))
    from outcomes import load_prices

    events = []
    import csv
    with open(ROOT / "data" / "placees.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            events.append(r)
    # 事件去重＋標記tier
    ev = {}
    for r in events:
        key = (r["stock_code"], r.get("ann_date"))
        if key[1] and key not in ev:
            ev[key] = r
    tier1_keys = {("00254", "2026-05-28"), ("02113", "2026-09-02")}
    if tier1 == "tier1":
        targets = [k for k in sorted(ev) if k in tier1_keys]
    else:
        # tier2：有具名承配人嘅事件（排除tier1已做）
        st = load_state()
        targets = [k for k in sorted(ev)
                   if k not in tier1_keys and st.get(f"{k[0]}|{k[1]}") is None
                   and any((x.get("placee_name") for x in events
                            if x["stock_code"] == k[0] and x.get("ann_date") == k[1]))]

    prices = load_prices()
    s = load_session()
    print(f"目標事件 {len(targets)} 宗（tier={tier1}）", flush=True)
    challenge_streak = 0
    for i, (code, ann_s) in enumerate(targets):
        ann = pd.Timestamp(ann_s).date()
        try:
            iid = get_issue_id(s, code)
        except ChallengeError as e:
            print(f"[{i+1}] CHALLENGE {code}: {e}", flush=True)
            FLAG_FILE.write_text(f"{code} issue_id lookup blocked", encoding="utf-8")
            break
        except Exception as e:
            print(f"[{i+1}] {code} ISSUE_ID_FAIL {e}", flush=True)
            continue
        dates = trading_dates(prices, code)
        if tier1 == "tier1":
            win = window_dates(dates, ann, 30, 60)
        else:
            win = window_dates(dates, ann, 10, 25)
        done = 0
        for d in win:
            key = f"{code}|{d.isoformat()}"
            st = load_state()
            if st.get(key):
                done += 1
                continue
            try:
                rows = fetch_day(s, iid, d.isoformat())
            except ChallengeError as e:
                print(f"CHALLENGE {key}: {e}", flush=True)
                FLAG_FILE.write_text(key, encoding="utf-8")
                challenge_streak += 1
                if challenge_streak >= 3:
                    print("連續挑戰失敗，停止（更新webb_cookie.txt後重跑）", flush=True)
                    sys.exit(2)
                continue
            challenge_streak = 0
            append_daily(code, d.isoformat(), rows)
            st = load_state()
            st[key] = len(rows)
            save_state(st)
            done += 1
        print(f"[{i+1}/{len(targets)}] {code} @{ann} 抓{done}/{len(win)}日", flush=True)


if __name__ == "__main__":
    main()
