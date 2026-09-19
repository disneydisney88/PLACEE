# -*- coding: utf-8 -*-
"""backfill_local_mysql.py — 用本機 CCASS MySQL（127.0.0.1:3307）補 Tier-2 佇列
中 ≤2025-12-24 嘅日期（webb-site dump，2.31億行holdings）。

 AGENTS.md：MySQL 8.0.46 喺 127.0.0.1:3307 root 免密碼 db=ccass；
 holdings(partID, issueID, holding, atDate)；participants(partID, CCASSID, partName)。
"""
import csv
import json
import pathlib
import sys

import pymysql

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "ccass"
LOCAL_WORK = CACHE / "local_work.json"
DAILY_CSV = CACHE / "ccass_daily.csv"
STATE = ROOT / "checkpoints" / "ccass_state.json"


def main():
    work = json.loads(LOCAL_WORK.read_text(encoding="utf-8"))
    print(f"本地MySQL工作項: {len(work)}", flush=True)
    con = pymysql.connect(host="127.0.0.1", port=3307, user="root",
                          password="", database="ccass", charset="utf8mb4")
    cur = con.cursor()
    new_daily = not DAILY_CSV.exists()
    n_rows = n_days = 0
    with open(DAILY_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "date", "participant_id",
                                          "participant_name", "shares", "pct"])
        if new_daily:
            w.writeheader()
        for it in work:
            cur.execute(
                """SELECT h.partID, p.CCASSID, p.partName, h.holding
                   FROM holdings h LEFT JOIN participants p ON p.partID = h.partID
                   WHERE h.issueID = %s AND h.atDate = %s
                   ORDER BY h.holding DESC""",
                (int(it["issue_id"]), it["date"]))
            rows = cur.fetchall()
            for partid, ccassid, name, holding in rows:
                w.writerow({"code": it["code"], "date": it["date"],
                            "participant_id": ccassid or f"P{partid}",
                            "participant_name": (name or "").strip(),
                            "shares": int(holding), "pct": None})
                n_rows += 1
            n_days += 1
    con.close()
    # state 標記
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    for it in work:
        st[f"{it['code']}|{it['date']}"] = -1  # -1 = 本地MySQL來源
    STATE.write_text(json.dumps(st), encoding="utf-8")
    print(f"併入 {n_days}日、{n_rows}行（pct需由shares/總發行股數計，偵測器已支援shares）",
          flush=True)


if __name__ == "__main__":
    main()
