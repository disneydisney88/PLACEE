# -*- coding: utf-8 -*-
"""detect_warehouse.py — Phase 2：CCASS 衛星倉偵測（規格§4.2）

偵測邏輯：
  對每宗事件視窗（Tier1 D-30..D+60；Tier2 D-10..D+25）：
  1) 建倉：非散戶白名單券商，持股% 由 <1% 升至 >3% 於 <=10 個交易日
  2) 派貨：其後 <=20 個交易日淨減 >50% 建倉量
  3) 同期散戶白名單合計上升 >2pt  → FLAG=衛星倉派貨
  COMBO_BSGS：B01666（寶新）與 B02014（粵商國際）同時在窗內出現且 >=0.5%
  （規格§4.3：本Project最高危組合，硬指標#4 = 00254/02113 必須命中）

輸出：data/warehouse_flags.csv
"""
import csv
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAILY_CSV = ROOT / "cache" / "ccass" / "ccass_daily.csv"
OUT_CSV = ROOT / "data" / "warehouse_flags.csv"

RETAIL = {
    "B01955": "富途", "B01668": "耀才", "B02159": "盈立", "B02142": "老虎",
    "B02175": "微牛", "B01584": "致富", "B02195": "長橋", "B01345": "輝立",
    "B01590": "盈透", "B01904": "華盛",
}
COMBO = ("B01666", "B02014")  # 寶新 + 粵商國際


def load_daily() -> pd.DataFrame:
    df = pd.read_csv(DAILY_CSV, dtype={"code": str, "participant_id": str})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["code", "date"])
    # 本地MySQL來源行冇pct（webb dump holdings無%欄）——用月度股本panel計
    n_null = int(df["pct"].isna().sum())
    if n_null and len(df):
        panel_p = ROOT / "data" / "input" / "shares_outstanding_panel_X0.csv"
        if panel_p.exists():
            pan = pd.read_csv(panel_p, dtype={"code": str}, encoding="utf-8-sig")
            pan["code"] = pan["code"].str.zfill(5)
            pan = pan[(pan["share_class"] == "TOTAL") & (pan["shares_outstanding"] > 0)]
            pan["month"] = pan["report_month"].astype(str).str[:7]
            issued = {(r["code"], r["month"]): int(r["shares_outstanding"])
                      for _, r in pan.iterrows()}
            def calc_pct(r):
                if pd.notna(r["pct"]) or pd.isna(r["shares"]) or r["shares"] <= 0:
                    return r["pct"]
                key = (r["code"], str(r["date"])[:7])
                tot = issued.get(key)
                # 當月冇panel就借前後月（carry-forward簡化）
                if tot is None:
                    y, m = int(key[5:7]), int(key[:4])
                    for dm in (-1, 1, -2, 2):
                        mm = m + dm
                        yy = y + (mm - 1) // 12
                        mm = (mm - 1) % 12 + 1
                        tot = issued.get((r["code"], f"{yy}-{mm:02d}"))
                        if tot:
                            break
                return round(r["shares"] / tot * 100, 4) if tot else None
            df["pct"] = df.apply(calc_pct, axis=1)
            print(f"pct由shares/股本panel計算: {n_null}行", flush=True)
    return df


def detect_event(df_code: pd.DataFrame, ann, combo_ids_present: dict) -> list[dict]:
    """df_code: 該股每日participant快照。回傳flag rows。"""
    flags = []
    dates = sorted(df_code["date"].unique())
    if len(dates) < 5:
        return flags
    # pivot: index=date, columns=participant_id, values=pct（前向填充）
    p = df_code.pivot_table(index="date", columns="participant_id",
                            values="pct", aggfunc="last")
    # 當日有快照但該券商缺席 = 0%；全日冇快照（停牌/缺日）= ffill
    has_snapshot = p.notna().any(axis=1)
    p = p.ffill()
    p[~has_snapshot] = pd.NA
    retail_cols = [c for c in p.columns if c in RETAIL]
    retail_sum = p[retail_cols].sum(axis=1, skipna=True) if retail_cols else pd.Series(0.0, index=p.index)

    # ---- COMBO_BSGS：兩券商同日同時出現 >=0.5%
    if all(cid in p.columns for cid in COMBO):
        both = p.loc[:, [c in COMBO for c in p.columns]].min(axis=1)
        hit_dates = both[both >= 0.5].index.tolist()
        if hit_dates:
            flags.append({
                "stock_code": df_code["code"].iloc[0],
                "event_date": ann,
                "broker_id": "B01666+B02014",
                "broker_name": "寶新+粵商國際(COMBO_BSGS)",
                "build_start": hit_dates[0].date().isoformat(),
                "build_peak_pct": round(float(
                    p.loc[hit_dates, list(COMBO)].max().max()), 2),
                "build_days": None,
                "dump_end": None, "dump_pct": None,
                "retail_delta_pct": None,
                "flag_level": "COMBO_BSGS",
            })

    # ---- 衛星倉建倉→派貨
    for pid in p.columns:
        if pid in RETAIL or pid in ("nan", None):
            continue
        series = p[pid].dropna()
        if len(series) < 6:
            continue
        idx_list = list(series.index)
        # 找「<1% → >3%」建倉穿越點（每個劇集只報一次）
        last_episode_end = -1
        for i in range(1, len(series)):
            if last_episode_end >= i:
                continue
            cur, prev = series.iloc[i], series.iloc[i - 1]
            if pd.isna(cur) or pd.isna(prev):
                continue
            if cur > 3.0 and prev < 1.0:
                gap = i - (i - 1)
                # 建倉起點：倒推最後一個<1%位置（距離<=10個交易日）
                j = i - 1
                while j >= 0 and (i - j) <= 10 and series.iloc[j] < 1.0:
                    j -= 1
                j += 1
                gap = i - j
                if gap <= 10:
                    peak = series.iloc[:i + 1].max()
                    after = series.iloc[i:i + 21]
                    end_idx = min(i + 21, len(series))
                    if len(after) >= 2:
                        end_val = after.iloc[-1]
                        dump_ratio = (peak - end_val) / peak if peak > 0 else 0
                        retail_win = retail_sum.reindex(after.index).ffill()
                        retail_delta = (retail_win.iloc[-1] - retail_win.iloc[0]
                                        if len(retail_win) >= 2 else 0)
                        if dump_ratio > 0.5:
                            # R7B精化（Claude覆核）：peak>=4%且高水位(>=3%)持有>=60日
                            # → 長期持倉調整，唔係衛星倉
                            ge3 = [x for x in series.iloc[i:end_idx] if x >= 3.0]
                            hold_days = (len(ge3) > 0) and (
                                (after.index[-1] - idx_list[j]).days >= 60)
                            if peak >= 4.0 and hold_days:
                                flevel = "長期持倉調整(非衛星)"
                            else:
                                flevel = ("衛星倉派貨" if retail_delta > 2.0
                                          else "建倉派貨(散戶升幅不足)")
                            flags.append({
                                "stock_code": df_code["code"].iloc[0],
                                "event_date": ann,
                                "broker_id": pid,
                                "broker_name": df_code[
                                    df_code["participant_id"] == pid
                                ]["participant_name"].iloc[0],
                                "build_start": idx_list[j].date().isoformat(),
                                "build_peak_pct": round(float(peak), 2),
                                "build_days": int(gap),
                                "dump_end": after.index[-1].date().isoformat(),
                                "dump_pct": round(float(dump_ratio * 100), 1),
                                "retail_delta_pct": round(float(retail_delta), 2),
                                "flag_level": flevel,
                            })
                    last_episode_end = i + 21
    return flags


def main():
    daily = load_daily()
    print(f"ccass_daily: {len(daily)}行, {daily['code'].nunique()}股", flush=True)
    events = set()
    with open(ROOT / "data" / "placees.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("ann_date"):
                events.add((r["stock_code"], r["ann_date"]))
    all_flags = []
    for (code, ann_s) in sorted(set(daily["code"]).intersection({c for c, _ in events})
                                and {(c, a) for (c, a) in events
                                     if c in set(daily["code"])}):
        df_code = daily[daily["code"] == code]
        ann = pd.Timestamp(ann_s).date()
        # 只分析含公告日附近視窗的數據（窗定義見fetch_ccass）
        dmin, dmax = df_code["date"].min().date(), df_code["date"].max().date()
        if not (dmin <= ann <= dmax or (dmax > ann)):
            continue
        flags = detect_event(df_code, ann, {})
        all_flags.extend(flags)
        for fl in flags:
            print(f"{code} @{ann} {fl['flag_level']}: {fl['broker_name']} "
                  f"peak={fl['build_peak_pct']}% dump={fl['dump_pct']}% "
                  f"retailΔ={fl['retail_delta_pct']}", flush=True)
    cols = ["stock_code", "event_date", "broker_id", "broker_name", "build_start",
            "build_peak_pct", "build_days", "dump_end", "dump_pct",
            "retail_delta_pct", "flag_level"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for fl in all_flags:
            w.writerow(fl)
    print(f"完成 → {OUT_CSV} 共{len(all_flags)}個flag", flush=True)


if __name__ == "__main__":
    main()
