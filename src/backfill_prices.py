# -*- coding: utf-8 -*-
"""backfill_prices.py — 用 webbsite-ccass-api（Yahoo源）補價格庫近期日線

價格庫(hk_prices_master.csv)截到2026-08-04；8月後公告事件（如02113@09-02）
嘅T+30/60/90結局需要近期日線。每股一次API call（limit=200），只補
ann_date >= 2026-07-01 嘅事件股。

輸出：cache/price_backfill.csv（code,date,open,high,low,close,volume,turnover）
"""
import csv
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, r"C:\Users\klcho\.zcode\workspace\default\ccass_task")

import ccass_api  # noqa: E402

BACKFILL_CSV = ROOT / "cache" / "price_backfill.csv"
CUTOFF = "2026-07-01"


def main():
    events = set()
    with open(ROOT / "data" / "placees.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("ann_date") and r["ann_date"] >= CUTOFF:
                events.add((r["stock_code"], r["ann_date"]))
    codes = sorted({c for c, _ in events})
    print(f"需backfill股票: {len(codes)}", flush=True)

    done = set()
    if BACKFILL_CSV.exists():
        with open(BACKFILL_CSV, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                done.add(r["code"])
    todo = [c for c in codes if c not in done]
    print(f"已完成 {len(done)}，待抓 {len(todo)}", flush=True)

    new_file = not BACKFILL_CSV.exists()
    n_rows = 0
    with open(BACKFILL_CSV, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "date", "open", "high", "low",
                                          "close", "volume", "turnover"])
        if new_file:
            w.writeheader()
        for i, code in enumerate(todo):
            try:
                d = ccass_api.call("/api/stock/price",
                                   {"code": code, "limit": 200,
                                    "start_date": CUTOFF},
                                   timeout=90, max_tries=3)
                rows = d.get("price_history") or d.get("rows") or []
                if isinstance(rows, dict):
                    rows = rows.get("history") or []
                for r in rows:
                    low = {str(k).lower(): v for k, v in r.items()}
                    close = low.get("close")
                    if close is None or close == "":
                        continue  # 冇收市價嘅行（停牌/未收市）唔入庫
                    w.writerow({"code": code,
                                "date": low.get("date"),
                                "open": low.get("open"), "high": low.get("high"),
                                "low": low.get("low"), "close": close,
                                "volume": low.get("volume"),
                                "turnover": low.get("turnover")
                                or low.get("turnover_est")})
                    n_rows += 1
                print(f"[{i+1}/{len(todo)}] {code} {len(rows)}行", flush=True)
            except Exception as e:
                print(f"[{i+1}/{len(todo)}] {code} FAIL {e}", flush=True)
    print(f"完成，新增{n_rows}行", flush=True)


if __name__ == "__main__":
    main()
