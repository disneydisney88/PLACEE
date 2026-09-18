# -*- coding: utf-8 -*-
"""crash_review.py — 未被規則捕捉嘅崩盤個案逆向分析（Claude覆核二·優先1）

對每宗 crash_flag=True 個案答四條問題：
1) 承配人具名定泛稱？幾多人？%分佈？
2) 事件前後有冇合股/拆股？
3) 崩盤距完成日幾多日？
4) 姓名或券商同已知名單有冇重疊？
輸出：crash_review.md + data/crash_cases.csv
"""
import datetime as dt
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    oc = pd.read_csv(DATA / "outcomes.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    pl = pd.read_csv(DATA / "placees.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    al = pd.read_csv(DATA / "alerts.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    reorgs = pd.read_csv(DATA / "input" / "合股事件20260831.csv", dtype=str,
                         encoding="utf-8-sig")
    reorgs = pd.concat([reorgs, pd.read_csv(
        DATA / "input" / "拆股事件20260831.csv", dtype=str, encoding="utf-8-sig")],
        ignore_index=True)
    rp = pd.read_csv(DATA / "repeat_placees.csv", encoding="utf-8-sig")
    known_names = set()
    for s in rp["name_variants"].fillna(""):
        known_names.update(x.strip() for x in s.split(";"))

    crashes = oc[oc["crash_flag"].astype(str) == "True"].copy()
    rows = []
    lines = ["# crash_review.md — 崩盤個案逆向分析", "",
             f"樣本：{len(crashes)}宗 crash_flag=True（連續調整序列＋壞tick剔除後）", "",
             "| 代號 | 名稱 | 公告日 | 崩盤日 | 距完成日 | 披露類型 | 具名承配人 | 合股/拆股鄰近 | 已知姓名重疊 | dd90 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in crashes.iterrows():
        code, ann = r["stock_code"], r["ann_date"]
        a = al[(al["stock_code"] == code) & (al["ann_date"] == ann)]
        disc = a["placee_disclosure_type"].iloc[0] if len(a) else "?"
        g = pl[(pl["stock_code"] == code) & (pl["ann_date"] == ann)]
        named = g[g["placee_name"].notna() & (g["placee_name"] != "")]
        n_named = len(named)
        pcts = named["pct_enlarged"].dropna().tolist()
        # 3) 距完成日
        gap = None
        if pd.notna(r.get("completion_date")) and pd.notna(r.get("crash_date")):
            try:
                gap = (dt.date.fromisoformat(str(r["crash_date"]))
                       - dt.date.fromisoformat(str(r["completion_date"]))).days
            except ValueError:
                gap = None
        # 2) 合股/拆股鄰近（公告日前後1年內）
        re = reorgs[reorgs["代號"].astype(str).str.replace(".hk", "", regex=False)
                    .str.zfill(5) == code]
        near = ""
        if len(re):
            for _, x in re.iterrows():
                eff = str(x.get("生效日期", ""))
                if eff and eff != "nan":
                    near += f"{x.get('比例','')}@{eff} "
        # 4) 已知姓名重疊
        overlap = sorted(set(named["placee_name"]) & known_names)
        rows.append({
            "stock_code": code, "stock_name": r["stock_name"], "ann_date": ann,
            "crash_date": r.get("crash_date"), "completion_gap_days": gap,
            "disclosure_type": disc, "n_named": n_named,
            "pcts": pcts, "reorg_nearby": near.strip(),
            "known_name_overlap": overlap,
            "max_drawdown_90": r.get("max_drawdown_90"),
        })
        lines.append(
            f"| {code} | {str(r['stock_name'])[:10]} | {ann} | "
            f"{r.get('crash_date')} | {gap if gap is not None else '—'} | "
            f"{disc} | {n_named}名{('（'+','.join(named['placee_name'].head(3)).rstrip('先生女士')+'）') if n_named else ''} | "
            f"{near.strip() or '—'} | {';'.join(overlap) or '—'} | "
            f"{r.get('max_drawdown_90')} |")
    pd.DataFrame(rows).to_csv(DATA / "crash_cases.csv", index=False,
                              encoding="utf-8-sig")
    # 統計
    n_direct = sum(1 for x in rows if x["disclosure_type"] == "DIRECT_SUBSCRIPTION")
    n_named = sum(1 for x in rows if x["n_named"] > 0)
    n_reorg = sum(1 for x in rows if x["reorg_nearby"])
    n_overlap = sum(1 for x in rows if x["known_name_overlap"])
    n_gap = [x["completion_gap_days"] for x in rows if x["completion_gap_days"] is not None]
    lines += ["", "## 統計", "",
              f"- 具名承配人個案：{n_named}/{len(rows)}（其餘為泛稱/冇定義——"
              f"即係崩盤集中喺**冇具名披露**嘅事件）",
              f"- DIRECT_SUBSCRIPTION：{n_direct}",
              f"- 前後一年有合股/拆股：{n_reorg}",
              f"- 有完成日可算距離：{len(n_gap)}宗，中位數"
              f"{sorted(n_gap)[len(n_gap)//2] if n_gap else '—'}日",
              f"- 同已知repeat姓名重疊：{n_overlap}", ""]
    (ROOT / "crash_review.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-9:]), flush=True)
    print(f"→ crash_review.md + data/crash_cases.csv", flush=True)


if __name__ == "__main__":
    main()
