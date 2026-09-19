# -*- coding: utf-8 -*-
"""build_registry.py — Phase 4：建立 registry.db（SQLite）

表：
  events     每宗事件（配股/供股輸入+輸出摘要）
  placees    承配人行（含source_url+snippet，可追溯）
  outcomes   結局標註
  wh_flags   CCASS 衛星倉/COMBO flag
  alerts     R1-R9 亮燈
  repeat_placees 同名候選
"""
import pathlib
import sqlite3

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "registry.db"


def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)

    pl = pd.read_csv(DATA / "placees.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    pl.to_sql("placees", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_pl_name ON placees(placee_name)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pl_code ON placees(stock_code, ann_date)")

    oc = pd.read_csv(DATA / "outcomes.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    oc.to_sql("outcomes", con, if_exists="replace", index=False)

    try:
        wf = pd.read_csv(DATA / "warehouse_flags.csv", dtype={"stock_code": str},
                         encoding="utf-8-sig")
        wf.to_sql("wh_flags", con, if_exists="replace", index=False)
    except Exception:
        pass

    al = pd.read_csv(DATA / "alerts.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    al.to_sql("alerts", con, if_exists="replace", index=False)

    rp = pd.read_csv(DATA / "repeat_placees.csv", encoding="utf-8-sig")
    rp.to_sql("repeat_placees", con, if_exists="replace", index=False)

    pgp = DATA / "post_go_placees.csv"
    if pgp.exists():
        pg = pd.read_csv(pgp, dtype={"stock_code": str}, encoding="utf-8-sig")
        pg.to_sql("post_go_placees", con, if_exists="replace", index=False)
        con.execute("CREATE INDEX IF NOT EXISTS idx_pg_name ON post_go_placees(placee_name)")

    # 視圖：姓名搜尋（含結局）
    has_pg = con.execute(
        "SELECT name FROM sqlite_master WHERE name='post_go_placees'").fetchone()
    pg_select = ""
    if has_pg:
        pg_select = '''
        UNION ALL
        SELECT g.placee_name, g.placee_type, g.stock_code, g.stock_name,
               g.ann_date, g.placee_label, g.shares, g.price, g.pct_enlarged,
               g.pct_enlarged_source, g.below_5pct, g.lockup, g.completion_date,
               g.source_url, g.snippet,
               NULL, NULL, NULL, NULL,
               g.go_ref, g.months_after_go, g.superseded
        FROM post_go_placees g
        WHERE g.placee_name IS NOT NULL AND g.placee_name != '' '''
    con.execute(f"""
    CREATE VIEW v_name_search AS
    SELECT * FROM (
        SELECT p.placee_name, p.placee_type, p.stock_code, p.stock_name,
               p.ann_date, p.placee_label, p.shares, p.price, p.pct_enlarged,
               p.pct_enlarged_source, p.below_5pct, p.lockup, p.completion_date,
               p.source_url, p.snippet,
               o.ret_ann_30, o.ret_ann_90, o.crash_flag, a.alert_score,
               NULL AS go_ref, NULL AS months_after_go, NULL AS superseded
        FROM placees p
        LEFT JOIN outcomes o ON o.stock_code = p.stock_code AND o.ann_date = p.ann_date
        LEFT JOIN alerts a ON a.stock_code = p.stock_code AND a.ann_date = p.ann_date
        WHERE p.placee_name IS NOT NULL AND p.placee_name != ''
        {pg_select}
    ) ORDER BY ann_date DESC
    """)
    con.commit()
    tables = ["placees", "outcomes", "wh_flags", "alerts", "repeat_placees"]
    if con.execute("SELECT name FROM sqlite_master WHERE name='post_go_placees'").fetchone():
        tables.append("post_go_placees")
    n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    print("registry.db:", n, flush=True)
    con.close()


if __name__ == "__main__":
    main()
