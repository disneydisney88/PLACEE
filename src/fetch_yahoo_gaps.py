# -*- coding: utf-8 -*-
"""fetch_yahoo_gaps.py — 用 Yahoo chart API 補 2024-2025初 事件股價格窗
（hk_prices_master 起點 2025-05-02；之前嘅 T+90 崩盤窗全部缺失）

AGENTS.md 實測：query1.finance.yahoo.com/v8/finance/chart/{code}.HK 可用（要UA header）。
輸出：cache/yahoo_gaps.csv (code,date,close)
outcomes.load_prices 會自動合併（cache/yahoo_gaps.csv 存在即併）。
"""
import csv
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "cache" / "yahoo_gaps.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch_yahoo(code: str, d1: dt.date, d2: dt.date) -> list[dict]:
    p1 = int(dt.datetime(d1.year, d1.month, d1.day).timestamp())
    p2 = int(dt.datetime(d2.year, d2.month, d2.day).timestamp()) + 86400
    sym = f"{int(code):04d}.HK"  # Yahoo HK 代码係4位（00254→0254.HK）
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?period1={p1}&period2={p2}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    res = data["chart"]["result"][0]
    ts = res.get("timestamp") or []
    closes = res["indicators"]["quote"][0].get("close") or []
    out = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = dt.date.fromtimestamp(t)
        out.append({"code": code, "date": d.isoformat(), "close": c})
    return out


def main():
    import pandas as pd
    pl = pd.read_csv(ROOT / "data" / "placees.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    pl["ann"] = pd.to_datetime(pl["ann_date"], errors="coerce")
    ev = pl.dropna(subset=["ann"]).drop_duplicates("stock_code")
    targets = ev[ev["ann"] < pd.Timestamp("2025-06-15")]
    print(f"需補價格股票: {len(targets)}", flush=True)
    seen_codes = set()
    if OUT.exists():
        done = pd.read_csv(OUT, dtype={"code": str})
        seen_codes = set(done["code"].unique())
    todo = [c for c in targets["stock_code"].unique() if c not in seen_codes]
    print(f"待抓: {len(todo)}", flush=True)
    new_file = not OUT.exists()
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "date", "close"])
        if new_file:
            w.writeheader()
        n_ok = 0
        for i, code in enumerate(todo):
            rows = ev[ev["stock_code"] == code]
            d_min = rows["ann"].min() - pd.Timedelta(days=15)
            d_max = rows["ann"].max() + pd.Timedelta(days=100)
            d_max = min(d_max, pd.Timestamp("2025-05-10"))
            if d_max <= d_min:
                continue
            try:
                data = fetch_yahoo(code, d_min.date(), d_max.date())
                for r in data:
                    w.writerow(r)
                f.flush()
                n_ok += 1
                print(f"[{i+1}/{len(todo)}] {code} {len(data)}行", flush=True)
            except Exception as e:
                print(f"[{i+1}/{len(todo)}] {code} FAIL {str(e)[:60]}", flush=True)
            time.sleep(1.2)
    print(f"完成: {n_ok} 隻股補齊", flush=True)


if __name__ == "__main__":
    main()
