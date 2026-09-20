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

import re

import pandas as pd

try:
    import opencc
    _cc = opencc.OpenCC("s2t")
    def _s2t(s): return _cc.convert(s)
except Exception:
    def _s2t(s): return s

RE_HONORIFIC = re.compile(r"(先生|女士|小姐|博士|教授|醫生|律師|太平紳士)$")


def name_key(name: str) -> str:
    """正規化姓名鍵：繁體＋去稱謂＋去空白（規格§九.3：統一轉繁體，原文另存）"""
    if not isinstance(name, str):
        return ""
    s = _s2t(name.strip())
    s = RE_HONORIFIC.sub("", s)
    return re.sub(r"\s+", "", s)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NOT_TESTED = "NOT_TESTED"

# 唔可能係承配人嘅機構名（泛稱定義body誤配——規格紀律：唔好有假名）
NAME_BLOCKLIST = [
    "香港聯合交易所", "聯交所", "香港交易及結算所", "香港中央結算",
    "HKSCC", "HKEX", "Stock Exchange", "The Stock Exchange",
]


def scrub_placees(path: pathlib.Path):
    """placees.csv 原地洗掃：機構名誤配清空＋完全重複行去重＋記錄原因。"""
    df = pd.read_csv(path, dtype={"stock_code": str}, encoding="utf-8-sig")
    n0 = len(df)
    key = ["event_id", "ann_date", "stock_code", "placee_label",
           "placee_name", "shares", "source_url"]
    df = df.drop_duplicates(subset=[c for c in key if c in df.columns], keep="first")
    n_dupes = n0 - len(df)
    mask = df["placee_name"].fillna("").apply(
        lambda n: any(b.lower() in str(n).lower() for b in NAME_BLOCKLIST))
    n = int(mask.sum())
    if n:
        df.loc[mask, "placee_name"] = ""
        df.loc[mask, "placee_type"] = "UNKNOWN"
        df["fail_reason"] = df["fail_reason"].astype(object)
        df.loc[mask, "fail_reason"] = "PLACEE_NAME_SCRUBBED(定義body為泛稱/機構)"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return n, n_dupes


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


def rule_r2_family(group: pd.DataFrame):
    """Claude覆核修正：R2拆三條，只食EXPLICIT來源pct（COMPUTED→R2_candidate）。

    R2a 貼線：任何單一個人承配人 4.0%<=pct<5.0%（n=1都中）
    R2b 均等：n>=2個人 AND cv=std/mean<0.05 AND max<5%
    R2c 隱形集合：sum(個人pct)>=10% AND 每個<5%
    回傳 (r2a, r2b, r2c, r2_candidate_computed, note)
    """
    g = group[group["placee_type"] == "個人"]
    if g.empty:
        return False, False, False, False, None
    # 三級制（Claude覆核二）：EXPLICIT/EXACT_COMPUTED可餵R2；ESTIMATED→candidate
    FEED = {"EXPLICIT", "EXACT_COMPUTED"}

    def _pcts(df):
        p = df[df["pct_enlarged"].notna()]
        if "pct_enlarged_source" in df.columns:
            p = p[p["pct_enlarged_source"].isin(FEED)]
        return p["pct_enlarged"].astype(float)

    p = _pcts(g)
    r2a = bool(((p >= 4.0) & (p < 5.0)).any()) if len(p) else False
    r2b = False
    if len(p) >= 2:
        mean = p.mean()
        if mean > 0 and p.max() < 5.0 and (p.std(ddof=0) / mean) < 0.05:
            r2b = True
    r2c = bool(len(p) and p.max() < 5.0 and p.sum() >= 10.0)
    # ESTIMATED pct（或舊COMPUTED標記）命中任何形態 → 只做候選，唔入 alert_score
    cand = False
    pc = g[(g["pct_enlarged"].notna())]
    if "pct_enlarged_source" in pc.columns:
        pc = pc[pc["pct_enlarged_source"].isin(["ESTIMATED", "COMPUTED"])]
    pc = pc["pct_enlarged"].astype(float)
    cand = bool(len(pc) and (
        ((pc >= 4.0) & (pc < 5.0)).any()
        or (len(pc) >= 2 and pc.max() < 5.0
            and pc.mean() > 0 and pc.std(ddof=0) / pc.mean() < 0.05)
        or (pc.max() < 5.0 and pc.sum() >= 10.0)))
    note = (f"n={len(p)} explicit/exact" if (r2a or r2b or r2c) else
            ("ESTIMATED pct命中(候選)" if cand else None))
    return r2a, r2b, r2c, cand, note


def main():
    pl, oc, wf = load_inputs()
    # 事件清單
    ev = pl.drop_duplicates(subset=["stock_code", "ann_date"])[
        ["stock_code", "ann_date", "stock_name", "ann_type", "mandate", "event_id"]]
    combo_stocks = set(wf[wf["flag_level"] == "COMBO_BSGS"]["stock_code"]) if len(wf) else set()
    satellite_stocks = set(wf[wf["flag_level"] == "衛星倉派貨"]["stock_code"]) if len(wf) else set()
    oc_by = {(r["stock_code"], r["ann_date"]): r for _, r in oc.iterrows()}

    # 披露類型分類（Claude覆核Q1）：DIRECT_SUBSCRIPTION / AGENT_SOURCED /
    # NONE(代價發行結構上無承配人) / NO_DEF
    def disclosure_type(eid: str) -> str:
        g = pl[pl["event_id"] == eid]
        if g["placee_name"].notna().any() and (g["placee_name"] != "").any():
            return "DIRECT_SUBSCRIPTION"
        fr = g["fail_reason"].fillna("").astype(str)
        if fr.str.contains("NO_NAMED_PLACEE").any():
            return "AGENT_SOURCED"
        if fr.str.contains("NO_PLACEE_DEF").any():
            return "NO_DEF"
        return "UNKNOWN"

    ev = ev.copy()
    ev["placee_disclosure_type"] = ev["event_id"].map(disclosure_type)

    rows = []
    for _, e in ev.iterrows():
        code, ann = e["stock_code"], e["ann_date"]
        g = pl[(pl["stock_code"] == code) & (pl["ann_date"] == ann)]
        o = oc_by.get((code, ann), {})
        r2a, r2b, r2c, r2cand, r2_note = rule_r2_family(g)

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
        # alert_score 只計高lift觸發訊號（rule_validation.md實證：R4 lift=0.55、
        # R8 lift≈1 為背景條件，按Claude覆核準則踢出評分，保留欄位做參考）
        score_terms = (code in combo_stocks, r2a, r2b, r2c,
                       code in satellite_stocks)
        rows.append({
            "event_id": e["event_id"],
            "stock_code": code, "stock_name": e["stock_name"],
            "ann_date": ann, "ann_type": e["ann_type"], "mandate": e["mandate"],
            "placee_disclosure_type": e["placee_disclosure_type"],
            "R1_combo_bsgs": code in combo_stocks,
            "R2a_near_5pct": r2a,
            "R2b_equal_split": r2b,
            "R2c_hidden_pool": r2c,
            "R2_candidate_computed_pct": r2cand,
            "R2_note": r2_note,
            "R3_offchain_block_25_30": NOT_TESTED,
            "R4_price_at_20pct_floor": r4,
            "R5_insider_sell_high": NOT_TESTED,
            "R6_director_sell_next_day": NOT_TESTED,
            "R7_satellite_dump": code in satellite_stocks,
            "R8_low_turnover_shell": r8,
            "R9_auction_anomaly": NOT_TESTED,
            "alert_score": sum(1 for v in score_terms if v),
            "n_placee_rows": len(g),
            "n_named_placees": int(g["placee_name"].notna().sum()),
            "price": price_ann if len(base) else None,
            "ret_ann_30": o.get("ret_ann_30"), "ret_ann_90": o.get("ret_ann_90"),
            "crash_flag": o.get("crash_flag"),
        })
    alert_df = pd.DataFrame(rows)

    # ---- DI實測證據合併（P4.5/P4.6）：data/di_evidence.csv（人手/瀏覽器實測）按
    # (stock_code, ann_date)左連接；有實測值覆寫NOT_TESTED，證據欄原樣帶入。
    # 放喺生成流程入面，令alerts.csv重生成都唔會沖走實測結果。
    di_path = DATA / "di_evidence.csv"
    if di_path.exists():
        di = pd.read_csv(
            di_path, dtype={"stock_code": str,
                            "R3_offchain_block_25_30": str,
                            "R5_insider_sell_high": str,
                            "R6_director_sell_next_day": str},
            encoding="utf-8-sig")
        ev_cols = ["R3_evidence", "R5_evidence", "R6_evidence"]
        val_cols = ["R3_offchain_block_25_30", "R5_insider_sell_high",
                    "R6_director_sell_next_day"]
        di = di[["stock_code", "ann_date"] + val_cols + ev_cols]
        alert_df = alert_df.merge(di, on=["stock_code", "ann_date"],
                                  how="left", suffixes=("", "_di"))
        for col in val_cols:
            d = alert_df[col + "_di"]
            alert_df[col] = d.where(d.notna(), alert_df[col])
            alert_df = alert_df.drop(columns=[col + "_di"])
        n_di = int(alert_df["R3_evidence"].notna().sum())
        print(f"DI實測證據合併：{n_di}行（data/di_evidence.csv）", flush=True)

    alert_df = alert_df.sort_values(["alert_score", "stock_code"],
                                    ascending=[False, True])
    alert_df.to_csv(DATA / "alerts.csv", index=False, encoding="utf-8-sig")
    n_hi = int((alert_df['alert_score'] >= 2).sum())
    print(f"alerts.csv: {len(alert_df)}事件，"
          f"高度警示(>=2，只計R1/R2/R7高lift訊號)：{n_hi}", flush=True)
    print(alert_df[alert_df['alert_score'] >= 2][
        ['stock_code', 'stock_name', 'ann_date', 'alert_score',
         'R1_combo_bsgs', 'R7_satellite_dump', 'R2_candidate_computed_pct']].to_string(index=False))
    dt_dist = alert_df['placee_disclosure_type'].value_counts().to_dict()
    print(f"披露類型分佈：{dt_dist}", flush=True)
    direct = alert_df[alert_df['placee_disclosure_type'] == 'DIRECT_SUBSCRIPTION']
    if len(direct):
        print(f"DIRECT_SUBSCRIPTION覆蓋KPI（規格§八.1意義上）："
              f"{len(direct)}宗", flush=True)

    # ---- 披露一致性交叉驗證（Claude覆核Q1第2條）：輸入CSV授權/代理 vs 解析結果
    try:
        import fetch_hkex as fh
        ev_input = {e['event_id']: e for e in fh.load_events()}
        checks = []
        for _, e in alert_df.iterrows():
            src = ev_input.get(e['event_id'])
            if not src:
                continue
            csv_agent = (src.get('agent_input') or '').strip()
            csv_direct_like = (csv_agent in ('', '-')) and \
                '代價' not in (src.get('ann_type_input') or '')
            checks.append({
                'event_id': e['event_id'], 'stock_code': e['stock_code'],
                'csv_agent': csv_agent,
                'csv_direct_like': csv_direct_like,
                'parsed_disclosure_type': e['placee_disclosure_type'],
                'mismatch': bool(csv_direct_like and
                                 e['placee_disclosure_type'] == 'AGENT_SOURCED'),
            })
        ck = pd.DataFrame(checks)
        ck.to_csv(DATA / 'disclosure_check.csv', index=False,
                  encoding='utf-8-sig')
        n_mis = int(ck['mismatch'].sum()) if len(ck) else 0
        print(f"disclosure_check.csv：{len(ck)}宗，"
              f"CSV話直接認購但解析得泛稱（真漏候選）={n_mis}宗",
              flush=True)
    except Exception as e:
        print(f"disclosure_check略過：{e}", flush=True)

    # ---- repeat_placees.csv（同名候選，規格§九.3/§九.4）
    # name_key=繁體＋去稱謂（付尚輝/付尚輝先生→同一鍵）；原文不變另存name_variants
    named = pl[pl["placee_name"].notna() & (pl["placee_name"] != "")].copy()
    named["name_key"] = named["placee_name"].map(name_key)
    named["case_tag"] = named["case_tag"].fillna(
        named["stock_code"] + "@" + named["ann_date"].astype(str))
    grp = named.groupby("name_key").agg(
        placee_name=("placee_name", "first"),
        name_variants=("placee_name", lambda x: "; ".join(sorted(set(x)))),
        n_stocks=("stock_code", "nunique"),
        n_events=("event_id", "nunique"),
        placee_type=("placee_type", lambda x: "/".join(sorted(set(x.dropna())))),
        cases=("case_tag", lambda x: "; ".join(sorted(set(x.dropna())))),
        stock_codes=("stock_code", lambda x: "; ".join(sorted(set(x)))),
    ).reset_index()
    grp = grp[grp["n_stocks"] >= 2].sort_values(
        ["n_stocks", "placee_name"], ascending=[False, True])
    grp = grp.drop(columns=["name_key"])
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
    n_scrub, n_dupes = scrub_placees(src)
    print(f"洗掃誤配承配人名：{n_scrub}行；去重重複行：{n_dupes}行", flush=True)
    main()
