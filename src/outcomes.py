# -*- coding: utf-8 -*-
"""outcomes.py — Phase 3：價格結局標註（T+30/60/90 等）

資料源：hk_prices_master.csv（tencent日線，含prev_close）
合股/拆股校正：合股事件/拆股事件20260831.csv（A:B = A股舊股 → B股新股；
  生效日前價格 × A/B 還原為新股口徑）— 規格§五警告（02113教訓）

輸出：data/outcomes.csv（每宗事件一行）
"""
import csv
import datetime as dt
import pathlib
import re
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = pathlib.Path(r"G:\我的雲端硬碟\STOCKSCAN\data\raw")
# 本地快取優先（G:虛擬碟首次讀會Errno 22）
PRICE_FILE = ROOT / "cache" / "hk_prices_master.csv"
if not PRICE_FILE.exists():
    PRICE_FILE = RAW / "hk_prices_master.csv"


def load_prices() -> pd.DataFrame:
    # 本地快取優先（G:虛擬碟首次讀會Errno 22）；合併8月後backfill（Yahoo源）
    base = ROOT / "cache" / "hk_prices_master.csv"
    if not base.exists():
        base = RAW / "hk_prices_master.csv"
    with open(base, encoding="utf-8-sig") as f:
        df = pd.read_csv(f, dtype={"code": str}, on_bad_lines="warn")
    bf = ROOT / "cache" / "price_backfill.csv"
    if bf.exists():
        with open(bf, encoding="utf-8-sig") as f:
            df2 = pd.read_csv(f, dtype={"code": str})
        df2 = df2[(df2["close"].notna()) & (df2["close"] > 0)]
        # backfill檔冇turnover_rate欄，對齊主庫欄位
        for col in df.columns:
            if col not in df2.columns:
                df2[col] = None
        df = pd.concat([df, df2[df.columns]], ignore_index=True)
        df = df.drop_duplicates(subset=["code", "date"], keep="last")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["code", "date"]).reset_index(drop=True)
    df["code"] = df["code"].str.zfill(5)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    return df


def load_reorg_factors() -> pd.DataFrame:
    """合股/拆股 → (code, effective_date, factor=A/B)。"""
    rows = []
    for fname, kind in [("合股事件20260831.csv", "cons"),
                        ("拆股事件20260831.csv", "split")]:
        p = DATA / "input" / fname
        if not p.exists():
            p = RAW / fname
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
        except Exception:
            continue
        for _, r in df.iterrows():
            m = re.search(r'(\d+)\s*:\s*(\d+)', str(r.get("比例", "")))
            eff = None
            ms = re.match(r'(\d{2})/(\d{2})/(\d{2})', str(r.get("生效日期", "")))
            if ms:
                yy = int(ms.group(3)) + (2000 if int(ms.group(3)) < 70 else 1900)
                try:
                    eff = dt.date(yy, int(ms.group(2)), int(ms.group(1)))
                except ValueError:
                    pass
            if m and eff:
                a, b = int(m.group(1)), int(m.group(2))
                if a > 0 and b > 0:
                    rows.append({"code": str(r.get("代號", "")).split(".")[0].zfill(5),
                                 "effective": eff, "factor": a / b, "kind": kind})
    return pd.DataFrame(rows)


def adjusted_series(prices: pd.DataFrame, reorgs: pd.DataFrame) -> pd.DataFrame:
    """加 adj_close 欄：生效日前價格乘以累積factor。"""
    df = prices.copy()
    df["adj_close"] = df["close"]
    if reorgs is None or reorgs.empty:
        return df
    for code, grp in reorgs.groupby("code"):
        idx = df.index[df["code"] == code]
        if len(idx) == 0:
            continue
        cum = 1.0
        for _, r in grp.sort_values("effective").iterrows():
            mask = df.loc[idx, "date"] < pd.Timestamp(r["effective"])
            df.loc[idx[mask.values], "adj_close"] *= r["factor"]
    return df


def find_t0(dates: list, ann: dt.date) -> int:
    """T0 = 公告日當日或之後首個交易日。"""
    for i, d in enumerate(dates):
        if d >= ann:
            return i
    return -1


def outcome_row(series: pd.DataFrame, t0: int, ann: dt.date,
                comp: dt.date | None) -> dict:
    dates = series["date"].dt.date.tolist()
    closes = series["adj_close"].astype(float).tolist()
    turns = series["turnover"].astype(float).tolist()
    n = len(dates)
    out = {"ret_ann_30": None, "ret_ann_60": None, "ret_ann_90": None,
           "ret_comp_13": None, "ret_comp_30": None, "ret_comp_60": None,
           "max_drawdown_90": None, "crash_flag": False, "crash_date": None,
           "vol_spike_ratio": None, "price_base": None,
           "price_base_prev": None, "turnover_median_prev90": None, "n_days": n}
    if t0 < 0:
        return out
    p0 = closes[t0]
    out["price_base"] = p0
    if t0 > 0:
        out["price_base_prev"] = closes[t0 - 1]
        import statistics
        seg90 = [t for t in turns[max(0, t0 - 90):t0]
                 if t is not None and not (isinstance(t, float) and pd.isna(t))]
        if seg90:
            out["turnover_median_prev90"] = int(statistics.median(seg90))
    for days, key in [(30, "ret_ann_30"), (60, "ret_ann_60"), (90, "ret_ann_90")]:
        i = min(t0 + days, n - 1)
        if i > t0 and p0:
            out[key] = round(closes[i] / p0 - 1, 4)
    if comp:
        for i in range(t0, n):
            if dates[i] >= comp:
                pc = closes[i]
                for days, key in [(13, "ret_comp_13"), (30, "ret_comp_30"),
                                  (60, "ret_comp_60")]:
                    j = min(i + days, n - 1)
                    if j > i and pc:
                        out[key] = round(closes[j] / pc - 1, 4)
                break
    # 90日內最大回撤（以T0收市為基準）＋單日>50%崩盤
    end = min(t0 + 90, n - 1)
    if end > t0 and p0:
        seg = closes[t0:end + 1]
        out["max_drawdown_90"] = round(min(seg) / p0 - 1, 4)
    prev = series["close"].astype(float).shift(1)
    for i in range(max(t0, 1), end + 1):
        pc = prev.iloc[i]
        if pc and pc > 0:
            r = closes[i] / pc - 1
            if r < -0.5:
                out["crash_flag"] = True
                out["crash_date"] = dates[i].isoformat()
                break
    # 成交額爆量：事件窗 D-1..D+10 最大 ÷ 前30交易日中位數
    med_start = max(0, t0 - 30)
    if t0 > 0:
        med = pd.Series(turns[med_start:t0]).median()
        win = turns[max(0, t0 - 1):min(n, t0 + 11)]
        if med and med > 0 and win:
            out["vol_spike_ratio"] = round(max(win) / med, 1)
    return out


def main():
    events = []
    with open(DATA / "placees.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            events.append(r)
    # 事件去重（每股每公告日一行）
    seen = {}
    for r in events:
        key = (r["stock_code"], r["ann_date"])
        if key not in seen and r.get("ann_date"):
            seen[key] = r
    print(f"事件數（去重）: {len(seen)}", flush=True)

    prices = load_prices()
    reorgs = load_reorg_factors()
    print(f"價格行數: {len(prices)}，股數: {prices['code'].nunique()}，"
          f"股本重組: {len(reorgs)}", flush=True)
    prices = adjusted_series(prices, reorgs)
    by_code = {c: g.reset_index(drop=True) for c, g in prices.groupby("code")}

    rows = []
    for (code, ann_s), ev in sorted(seen.items()):
        row = {"stock_code": code, "stock_name": ev.get("stock_name", ""),
               "ann_date": ann_s, "completion_date": ev.get("completion_date") or None,
               "event_id": ev.get("event_id"), "price_source": "hk_prices_master.csv(tencent)"}
        ann = dt.date.fromisoformat(ann_s)
        comp = None
        if row["completion_date"]:
            try:
                comp = dt.date.fromisoformat(row["completion_date"])
            except ValueError:
                comp = None
        g = by_code.get(code)
        if g is None or len(g) == 0:
            row["fail_reason"] = "NO_PRICE_DATA"
            rows.append(row)
            continue
        dates = g["date"].dt.date.tolist()
        t0 = find_t0(dates, ann)
        if t0 < 0:
            row["fail_reason"] = "ANN_DATE_AFTER_LAST_PRICE"
            rows.append(row)
            continue
        row.update(outcome_row(g, t0, ann, comp))
        row["fail_reason"] = None
        rows.append(row)
        print(f"{code} {ann_s} base={row.get('price_base')} "
              f"r30={row.get('ret_ann_30')} r90={row.get('ret_ann_90')} "
              f"dd={row.get('max_drawdown_90')} crash={row.get('crash_flag')}", flush=True)

    cols = ["stock_code", "stock_name", "ann_date", "completion_date", "event_id",
            "price_base", "price_base_prev",
            "ret_ann_30", "ret_ann_60", "ret_ann_90",
            "ret_comp_13", "ret_comp_30", "ret_comp_60",
            "max_drawdown_90", "crash_flag", "crash_date",
            "vol_spike_ratio", "turnover_median_prev90",
            "price_source", "fail_reason"]
    with open(DATA / "outcomes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"完成 → data/outcomes.csv 共{len(rows)}行", flush=True)


if __name__ == "__main__":
    main()
