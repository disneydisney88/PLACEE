# -*- coding: utf-8 -*-
"""alerts.py — Phase 4：交叉索引＋亮燈引擎（規格§6）

規則（每條獨立布林欄；NOT_TESTED 唔可以留空或估——規格§6.3）：
  R1 寶新(B01666)+粵商國際(B02014)同時出現   ← warehouse_flags COMBO_BSGS
  R2 多名自然人承配人、分配均等且全部<5%      ← placees（stddev<0.1, max<5, n>=3）
  R3 控股塊場外易手25-29.99%                 ← NOT_TESTED（需DI）
  R4 配售價貼20%折讓下限（差距<2%）          ← price vs base_prev*0.8
  R5 既有股東/董事高價離場                   ← NOT_TESTED（需DI）
  R6 利好翌日董事場內減持                    ← NOT_TESTED（需DI）
  R7 衛星倉派貨                             ← warehouse_flags
  R8 事件前長期低成交殼（前90日中位數<50萬）  ← outcomes
  R9 競價異常U盤                             ← NOT_TESTED（需逐筆）

輸出：data/alerts.csv、data/repeat_placees.csv
"""
import csv
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NOT_TESTED = "NOT_TESTED"

# 唔可能係承配人嘅機構名（泛稱定義body誤配——規格紀律：唔好有假名）
NAME_BLOCKLIST = [
    "香港聯合交易所", "聯交所", "香港交易及結算所", "香港中央結算",
    "HKSCC", "HKEX", "Stock Exchange", "The Stock Exchange",
]


def scrub_placees(path: pathlib.Path):
    """placees.csv 原地洗掃：機構名誤配嘅placee_name清空＋記錄原因。"""
    df = pd.read_csv(path, dtype={"stock_code": str}, encoding="utf-8-sig")
    mask = df["placee_name"].fillna("").apply(
        lambda n: any(b.lower() in str(n).lower() for b in NAME_BLOCKLIST))
    n = int(mask.sum())
    if n:
        df.loc[mask, "placee_name"] = ""
        df.loc[mask, "placee_type"] = "UNKNOWN"
        df["fail_reason"] = df["fail_reason"].astype(object)
        df.loc[mask, "fail_reason"] = "PLACEE_NAME_SCRUBBED(定義body為泛稱/機構)"
        df.to_csv(path, index=False, encoding="utf-8-sig")
    return n


def load_inputs():
    pl = pd.read_csv(DATA / "placees.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    oc = pd.read_csv(DATA / "outcomes.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    try:
        wf = pd.read_csv(DATA / "warehouse_flags.csv", dtype={"stock_code": str},
                         encoding="utf-8-sig")
    except Exception:
        wf = pd.DataFrame(columns=["stock_code", "event_date", "flag_level"])
    return pl, oc, wf


def rule_r2(group: pd.DataFrame):
    g = group[group["placee_type"] == "個人"]
    if len(g) < 3:
        return False, None
    pcts = g["pct_enlarged"]
    if pcts.isna().any():
        return False, None  # 有承配人冇%數據 → 唔可以證實均等
    if pcts.max() < 5.0 and pcts.std(ddof=0) < 0.1:
        return True, f"{len(g)}名個人, max={pcts.max():.2f}%, std={pcts.std(ddof=0):.3f}"
    return False, None


def main():
    pl, oc, wf = load_inputs()
    # 事件清單
    ev = pl.drop_duplicates(subset=["stock_code", "ann_date"])[
        ["stock_code", "ann_date", "stock_name", "ann_type", "mandate", "event_id"]]
    combo_stocks = set(wf[wf["flag_level"] == "COMBO_BSGS"]["stock_code"]) if len(wf) else set()
    satellite_stocks = set(wf[wf["flag_level"] == "衛星倉派貨"]["stock_code"]) if len(wf) else set()
    oc_by = {(r["stock_code"], r["ann_date"]): r for _, r in oc.iterrows()}

    rows = []
    for _, e in ev.iterrows():
        code, ann = e["stock_code"], e["ann_date"]
        g = pl[(pl["stock_code"] == code) & (pl["ann_date"] == ann)]
        o = oc_by.get((code, ann), {})
        r2_hit, r2_note = rule_r2(g)

        r4 = None
        price = o.get("price_base_prev")
        base = g["price"].dropna()
        price_ann = base.iloc[0] if len(base) else None
        if price and price_ann and price > 0:
            ratio = price_ann / (float(price) * 0.8)
            r4 = bool(0.98 <= ratio <= 1.02)
        r8 = None
        med = o.get("turnover_median_prev90")
        if med is not None and not pd.isna(med):
            r8 = bool(float(med) < 500_000)
        rows.append({
            "stock_code": code, "stock_name": e["stock_name"],
            "ann_date": ann, "ann_type": e["ann_type"], "mandate": e["mandate"],
            "R1_combo_bsgs": code in combo_stocks,
            "R2_equal_small_individuals": r2_hit, "R2_note": r2_note,
            "R3_offchain_block_25_30": NOT_TESTED,
            "R4_price_at_20pct_floor": r4,
            "R5_insider_sell_high": NOT_TESTED,
            "R6_director_sell_next_day": NOT_TESTED,
            "R7_satellite_dump": code in satellite_stocks,
            "R8_low_turnover_shell": r8,
            "R9_auction_anomaly": NOT_TESTED,
            "alert_score": sum(1 for v in (
                code in combo_stocks, r2_hit, r4 if r4 is not None else False,
                code in satellite_stocks, r8 if r8 is not None else False) if v),
            "n_placee_rows": len(g),
            "n_named_placees": int(g["placee_name"].notna().sum()),
            "price": price_ann if len(base) else None,
            "ret_ann_30": o.get("ret_ann_30"), "ret_ann_90": o.get("ret_ann_90"),
            "crash_flag": o.get("crash_flag"),
        })
    alert_df = pd.DataFrame(rows)
    alert_df = alert_df.sort_values(["alert_score", "stock_code"],
                                    ascending=[False, True])
    alert_df.to_csv(DATA / "alerts.csv", index=False, encoding="utf-8-sig")
    print(f"alerts.csv: {len(alert_df)}事件，高度警示(>=3)："
          f"{int((alert_df['alert_score'] >= 3).sum())}", flush=True)
    print(alert_df[alert_df['alert_score'] >= 3][
        ['stock_code', 'stock_name', 'ann_date', 'alert_score']].to_string(index=False))

    # ---- repeat_placees.csv（同名候選清單，唔自動合併——規格§九.4）
    named = pl[pl["placee_name"].notna() & (pl["placee_name"] != "")]
    grp = named.groupby("placee_name").agg(
        n_stocks=("stock_code", "nunique"),
        n_events=("event_id", "nunique"),
        placee_type=("placee_type", lambda x: "/".join(sorted(set(x.dropna())))),
        cases=("case_tag", lambda x: "; ".join(sorted(set(x.dropna())))),
        stock_codes=("stock_code", lambda x: "; ".join(sorted(set(x)))),
    ).reset_index()
    grp = grp[grp["n_stocks"] >= 2].sort_values(
        ["n_stocks", "placee_name"], ascending=[False, True])
    grp.to_csv(DATA / "repeat_placees.csv", index=False, encoding="utf-8-sig")
    print(f"repeat_placees.csv: {len(grp)}個跨股姓名（候選，需人手判斷）", flush=True)
    if len(grp):
        print(grp.head(20).to_string(index=False))


if __name__ == "__main__":
    # placees.csv 補 case_tag（code@ann_date）供合併用＋機構名誤配洗掃
    src = DATA / "placees.csv"
    df = pd.read_csv(src, dtype={"stock_code": str}, encoding="utf-8-sig")
    df["case_tag"] = df["stock_code"] + "@" + df["ann_date"].astype(str)
    df.to_csv(src, index=False, encoding="utf-8-sig")
    n = scrub_placees(src)
    print(f"洗掃誤配承配人名：{n}行", flush=True)
    main()
