# -*- coding: utf-8 -*-
"""ingest_browser_results.py — 將瀏覽器導航抓取結果併入 ccass_daily.csv＋state

browser_results.jsonl 每行：{code,date,ok,n,rows:[{participant_id,participant_name,shares,pct}]}
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "ccass"
DAILY_CSV = CACHE / "ccass_daily.csv"
RESULTS = CACHE / "browser_results.jsonl"
STATE = ROOT / "checkpoints" / "ccass_state.json"


def main():
    if not RESULTS.exists():
        print("冇 results 檔")
        return
    n_rows = n_days = 0
    days = {}
    with open(RESULTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not r.get("ok"):
                continue
            days[(r["code"], r["date"])] = r.get("rows") or []
    new_daily = not DAILY_CSV.exists()
    with open(DAILY_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "date", "participant_id",
                                          "participant_name", "shares", "pct"])
        if new_daily:
            w.writeheader()
        for (code, date), rows in sorted(days.items()):
            for rr in rows:
                w.writerow({"code": code, "date": date, **rr})
                n_rows += 1
            n_days += 1
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for (code, date) in days:
        st[f"{code}|{date}"] = len(days[(code, date)])
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st), encoding="utf-8")
    tmp.replace(STATE)
    # 清空已併入嘅results
    RESULTS.unlink()
    print(f"併入 {n_days}日、{n_rows}行；state總數 {len(st)}")


if __name__ == "__main__":
    main()
