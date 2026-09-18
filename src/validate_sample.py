# -*- coding: utf-8 -*-
"""validate_sample.py — H4：抽樣驗證（規格§八.2：30宗，姓名及股數準確率≥90%）

方法：
1. 抽30宗「有具名承配人」事件（隨機seed固定，可重現）
2. 客觀檢查：placee_name是否出現於該行snippet（姓名與原文一致性）
             shares若有值，是否為正整數且在公告股數常見範圍
3. 人工複核表輸出 parser_report.md（agent逐條對snippet核）
"""
import pathlib
import random
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    pl = pd.read_csv(DATA / "placees.csv", dtype={"stock_code": str},
                     encoding="utf-8-sig")
    named = pl[pl["placee_name"].notna() & (pl["placee_name"] != "")]
    events = named.drop_duplicates(subset=["stock_code", "ann_date"])
    sample = events.sample(n=min(30, len(events)), random_state=42)

    rows = []
    n_name_ok = n_name_checked = n_shares_ok = n_shares_checked = 0
    for _, ev in sample.iterrows():
        g = named[(named["stock_code"] == ev["stock_code"])
                  & (named["ann_date"] == ev["ann_date"])]
        for _, r in g.iterrows():
            name = str(r["placee_name"])
            snippet = str(r.get("snippet", "") or "")
            name_ok = name.replace("先生", "").replace("女士", "") in snippet
            n_name_checked += 1
            n_name_ok += int(name_ok)
            shares_ok = None
            if pd.notna(r.get("shares")):
                n_shares_checked += 1
                shares_ok = bool(float(r["shares"]) > 0 and float(r["shares"]) == int(float(r["shares"])))
                n_shares_ok += int(shares_ok)
            rows.append({
                "stock_code": r["stock_code"], "stock_name": r["stock_name"],
                "ann_date": r["ann_date"], "label": r["placee_label"],
                "name": name, "name_in_snippet": name_ok,
                "shares": r.get("shares"), "shares_positive_int": shares_ok,
                "pct_enlarged": r.get("pct_enlarged"),
                "confidence": r.get("parse_confidence"),
                "snippet": snippet[:200],
            })
    df = pd.DataFrame(rows)
    acc_name = n_name_ok / max(n_name_checked, 1)
    acc_shares = n_shares_ok / max(n_shares_checked, 1)
    with open(ROOT / "parser_report.md", "w", encoding="utf-8") as f:
        f.write("# parser_report.md — 承配人抽取抽樣驗證\n\n")
        f.write(f"抽樣：{len(sample)}宗事件（seed=42）、{len(df)}行承配人記錄\n\n")
        f.write(f"- 姓名一致性（name出現於該行snippet）：{n_name_ok}/{n_name_checked} = {acc_name:.1%}\n")
        f.write(f"- 股數格式（正整數）：{n_shares_ok}/{n_shares_checked} = {acc_shares:.1%}\n\n")
        f.write("逐條人工複核表（agent對snippet核對姓名/股數/標籤）：\n\n")
        for _, r in df.iterrows():
            f.write(f"### {r['stock_code']} {r['stock_name']} @ {r['ann_date']}\n")
            f.write(f"- label={r['label']} name={r['name']} shares={r['shares']} "
                    f"pct={r['pct_enlarged']} conf={r['confidence']}\n")
            f.write(f"- name_in_snippet={r['name_in_snippet']}\n")
            f.write(f"- snippet: {r['snippet']}\n\n")
    print(f"樣本{len(sample)}事件/{len(df)}行；姓名一致性{acc_name:.1%}；"
          f"股數格式{acc_shares:.1%}", flush=True)
    print("→ parser_report.md", flush=True)


if __name__ == "__main__":
    main()
