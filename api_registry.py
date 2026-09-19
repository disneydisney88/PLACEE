# -*- coding: utf-8 -*-
"""api_registry.py — PLACEE registry API（FastAPI，7個GET endpoint＋reload）

跑法：uvicorn api_registry:app --host 0.0.0.0 --port 8765
DB：data/registry.db（隨repo；/registry/reload可重開）
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import fastapi
from fastapi import HTTPException, Header, Query

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "registry.db"

app = fastapi.FastAPI(title="PLACEE registry API", version="1.0.0",
                      description="承配人索引庫查詢層（所有數字可追溯source_url）")

_conn: sqlite3.Connection | None = None
_db_mtime: float = 0.0


def db() -> sqlite3.Connection:
    global _conn, _db_mtime
    mtime = DB.stat().st_mtime if DB.exists() else 0
    if _conn is None or mtime != _db_mtime:
        if _conn is not None:
            _conn.close()
        if not DB.exists():
            raise HTTPException(503, "registry.db 不存在（等bootstrap或/registry/reload）")
        _conn = sqlite3.connect(str(DB))
        _conn.row_factory = sqlite3.Row
        _db_mtime = mtime
    return _conn


def rows(q: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in db().execute(q, args).fetchall()]


@app.get("/registry/meta")
def meta():
    c = db()
    return {
        "db_file": str(DB),
        "db_updated": datetime.fromtimestamp(_db_mtime).isoformat() if _db_mtime else None,
        "n_placee_rows": c.execute("SELECT COUNT(*) FROM placees").fetchone()[0],
        "n_named": c.execute(
            "SELECT COUNT(*) FROM placees WHERE placee_name IS NOT NULL "
            "AND placee_name != ''").fetchone()[0],
        "n_events": c.execute(
            "SELECT COUNT(DISTINCT event_id) FROM placees").fetchone()[0],
        "n_brokers_flagged": c.execute(
            "SELECT COUNT(DISTINCT broker_id) FROM wh_flags").fetchone()[0],
        "rule_version": "R1+R2a/b/c+R7 scored; R4/R8 recorded not scored; R3/R5/R6/R9 NOT_TESTED",
    }


@app.get("/registry/name")
def registry_name(q: str = Query(..., min_length=1)):
    """承配人姓名模糊查詢（中英文；name_key已做繁簡＋稱謂正規化）。"""
    like = f"%{q}%"
    return rows(
        """SELECT placee_name, placee_type, stock_code, stock_name, ann_date,
                  placee_label, shares, price, pct_enlarged, pct_enlarged_source,
                  below_5pct, completion_date, alert_score,
                  source_url, snippet
           FROM v_name_search
           WHERE placee_name LIKE ? OR placee_name LIKE ?
           ORDER BY ann_date DESC""", (like, like))


@app.get("/registry/broker")
def registry_broker(q: str = Query(..., min_length=2)):
    """券商查詢：CCASS衛星倉flag（broker_id或名稱模糊）。"""
    like = f"%{q.upper()}%"
    return rows(
        """SELECT stock_code, event_date, broker_id, broker_name, build_start,
                  build_peak_pct, build_days, dump_end, dump_pct,
                  retail_delta_pct, flag_level
           FROM wh_flags
           WHERE UPPER(broker_id) LIKE ? OR UPPER(broker_name) LIKE ?
           ORDER BY event_date DESC""", (like, like))


@app.get("/registry/stock/{code}")
def registry_stock(code: str):
    code = code.zfill(5)
    events = rows(
        """SELECT DISTINCT event_id, ann_date, ann_type, mandate, fail_reason
           FROM placees WHERE stock_code=? ORDER BY ann_date""", (code,))
    placees = rows(
        """SELECT placee_label, placee_name, placee_type, beneficial_owner,
                  shares, price, pct_enlarged, pct_enlarged_source, below_5pct,
                  lockup, completion_date, source_url, snippet, parse_confidence
           FROM placees WHERE stock_code=? ORDER BY ann_date, placee_label""",
        (code,))
    alert = rows("SELECT * FROM alerts WHERE stock_code=?", (code,))
    flags = rows("SELECT * FROM wh_flags WHERE stock_code=?", (code,))
    outcome = rows("SELECT * FROM outcomes WHERE stock_code=?", (code,))
    post_go = rows(
        """SELECT go_ref, go_name, ann_date, months_after_go, superseded,
                  ann_title, placee_label, placee_name, placee_type,
                  shares, completion_date, source_url
           FROM post_go_placees WHERE stock_code=? ORDER BY ann_date""", (code,))
    return {"stock_code": code, "events": events, "placees": placees,
            "alerts": alert, "wh_flags": flags, "outcomes": outcome,
            "post_go": post_go}


@app.get("/registry/alerts")
def registry_alerts(since: str = Query("2000-01-01")):
    return rows(
        """SELECT * FROM alerts
           WHERE ann_date >= ? AND alert_score >= 1
           ORDER BY alert_score DESC, ann_date DESC""", (since,))


@app.get("/registry/repeat")
def registry_repeat(min_count: int = 2):
    out = rows(
        """SELECT placee_name, name_variants, n_stocks, n_events, placee_type,
                  cases, stock_codes
           FROM repeat_placees WHERE n_stocks >= ?
           ORDER BY n_stocks DESC""", (min_count,))
    return {"note": "同名候選清單，唔代表同一人（規格§九.4）", "rows": out}


@app.get("/registry/crash")
def registry_crash(days: int = 30, threshold: float = -0.5):
    """承配後N日內跌幅超過門檻嘅個案。

    口徑：crash_flag（90日內單日跌>50%，連續調整序列＋壞tick剔除）
    或 max_drawdown_90 <= threshold。注意：02113事件日2026-09-02，
    價格數據窗只到2026-09-18，其後走勢未包含——數據齊後重跑outcomes自動補足。
    """
    out = rows(
        """SELECT o.stock_code, o.stock_name, o.ann_date, o.completion_date,
                  o.crash_date, o.max_drawdown_90, o.crash_suspect_tick,
                  o.ret_ann_30, o.price_base,
                  a.alert_score, a.placee_disclosure_type
           FROM outcomes o LEFT JOIN alerts a
             ON a.stock_code = o.stock_code AND a.ann_date = o.ann_date
           WHERE o.crash_flag = 1 OR o.max_drawdown_90 <= ?
           ORDER BY o.max_drawdown_90""", (threshold,))
    for r in out:
        r["within_days_param"] = days
    return {"note": "02113@2026-09-02價格窗至09-18（crash_flag=False為數據窗所限，非安全訊號）",
            "rows": out}


@app.get("/registry/post_go")
def registry_post_go(months: int = 12):
    """GO（全購要約）完成後N個月內出現嘅承配人——「接手人網絡」。

    按出現次數排序；superseded=1 為中途退出/被替代記錄（保留做網絡線索）。
    """
    return rows(
        """SELECT placee_name, placee_type, COUNT(*) n_cases,
                  GROUP_CONCAT(DISTINCT stock_code) stocks,
                  GROUP_CONCAT(DISTINCT go_ref) go_refs,
                  MIN(months_after_go) first_months_after_go,
                  MAX(CASE WHEN superseded = 0 OR superseded IS NULL
                           THEN 0 ELSE 1 END) ever_superseded
           FROM post_go_placees
           WHERE placee_name IS NOT NULL AND placee_name != ''
             AND (months_after_go IS NULL OR months_after_go <= ?)
           GROUP BY placee_name
           ORDER BY n_cases DESC, placee_name""", (months,))


@app.post("/registry/reload")
def reload_db(x_token: str = Header(default="")):
    token = os.environ.get("PLACEE_API_TOKEN", "")
    if token and x_token != token:
        raise HTTPException(401, "bad token")
    global _conn, _db_mtime
    if _conn is not None:
        _conn.close()
    _conn, _db_mtime = None, 0.0
    db()
    return {"reloaded": True}
