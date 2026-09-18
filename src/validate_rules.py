# -*- coding: utf-8 -*-
"""validate_rules.py — 規則實證校準（Claude覆核第1優先：lift表）

對每條規則計：支持度、P(crash|R)、基準率P(crash)、lift；
另用「T+30回報<=-30%」做第二個結果指標（崩盤旗可能漏陰跌）。
輸出 rule_validation.md：lift<1.5嘅規則建議砍走或重設門檻。
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

RULES = [
    ("R1_combo_bsgs", "R1 寶新+粵商國際"),
    ("R2a_near_5pct", "R2a 貼線(4-5%)"),
    ("R2b_equal_split", "R2b 均等分配"),
    ("R2c_hidden_pool", "R2c 隱形集合(Σ>=10%)"),
    ("R4_price_at_20pct_floor", "R4 貼20%折讓底"),
    ("R7_satellite_dump", "R7 衛星倉派貨"),
    ("R8_low_turnover_shell", "R8 低成交殼"),
]
RULE_COLS = [r[0] for r in RULES]


def lift_table(alerts: pd.DataFrame, outcomes: pd.DataFrame,
               outcome_col: str, base_rate: float) -> pd.DataFrame:
    rule_cols = [c for c in alerts.columns if c.startswith("R") and
                 c[1:2].isdigit()] or []
    keep = ["stock_code", "ann_date"] + [c for c in RULE_COLS if c in alerts.columns]
    m = alerts[keep].merge(outcomes[["stock_code", "ann_date", outcome_col]],
                           on=["stock_code", "ann_date"], how="left")
    sub = m[m[outcome_col].notna()]
    rows = []
    for col, label in RULES:
        if col not in sub.columns:
            continue
        hit = sub[sub[col] == True]  # noqa: E712
        n = int((sub[col] == True).sum())  # noqa: E712
        if n == 0 or len(sub) == 0:
            rows.append({"規則": label, "支持度": n, "P(結果|規則)": None,
                         "基準率": round(base_rate, 3), "lift": None})
            continue
        p = float((hit[outcome_col] == True).mean()) if outcome_col == "crash_flag" \
            else float((pd.to_numeric(hit[outcome_col]) <= -0.30).mean())
        lift = p / base_rate if base_rate > 0 else None
        rows.append({"規則": label, "支持度": n, "P(結果|規則)": round(p, 3),
                     "基準率": round(base_rate, 3),
                     "lift": round(lift, 2) if lift else None})
    return pd.DataFrame(rows)


def continuous_table(alerts: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """連續outcome檢定（Claude覆核二·#4）：規則命中組 vs 未命中組
    ret_ann_90 / max_drawdown_90 中位數差＋Mann-Whitney U（二元crash太稀疏）。"""
    from scipy.stats import mannwhitneyu
    keep = ["stock_code", "ann_date"] + [c for c in RULE_COLS if c in alerts.columns]
    m = alerts[keep].merge(
        outcomes[["stock_code", "ann_date", "ret_ann_90", "max_drawdown_90"]],
        on=["stock_code", "ann_date"], how="left")
    rows = []
    for col, label in RULES:
        if col not in m.columns:
            continue
        hit = m[m[col] == True]  # noqa: E712
        miss = m[m[col] != True]  # noqa: E712
        row = {"規則": label, "支持度": len(hit)}
        for outcome in ("ret_ann_90", "max_drawdown_90"):
            h = pd.to_numeric(hit[outcome], errors="coerce").dropna()
            mi = pd.to_numeric(miss[outcome], errors="coerce").dropna()
            key = "中位數" + ("ret90" if outcome == "ret_ann_90" else "dd90")
            if len(h) < 3 or len(mi) < 3:
                row[key] = None
                row["p(" + key + ")"] = None
                continue
            row[key] = round(float(h.median()) - float(mi.median()), 3)
            try:
                u, pv = mannwhitneyu(h, mi, alternative="two-sided")
                row["p(" + key + ")"] = round(float(pv), 4)
            except Exception:
                row["p(" + key + ")"] = None
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    alerts = pd.read_csv(DATA / "alerts.csv", dtype={"stock_code": str},
                         encoding="utf-8-sig")
    outcomes = pd.read_csv(DATA / "outcomes.csv", dtype={"stock_code": str},
                           encoding="utf-8-sig")
    oc = outcomes.copy()
    oc["crash_flag"] = oc["crash_flag"].astype(str).map({"True": True, "False": False})
    base_crash = float((oc["crash_flag"] == True).sum()  # noqa: E712
                       / max(oc["crash_flag"].notna().sum(), 1))
    oc30 = oc[oc["ret_ann_30"].notna()]
    base_tail30 = float((pd.to_numeric(oc30["ret_ann_30"]) <= -0.30).mean()
                        / 1.0) if len(oc30) else 0.0

    t_crash = lift_table(alerts, oc, "crash_flag", base_crash)
    t_tail = lift_table(alerts, oc, "ret_ann_30", base_tail30)
    t_cont = continuous_table(alerts, oc)

    lines = ["# rule_validation.md — 規則實證校準（lift表）", "",
             f"樣本：{len(alerts)}事件（有結局數據者入表）", "",
             f"基準率：P(crash)={base_crash:.3f}；"
             f"P(T+30<=-30%)={base_tail30:.3f}", "",
             "## 結果一：crash_flag（90日內單日>50%跌）", "",
             t_crash.to_markdown(index=False), "",
             "## 結果二：T+30回報<=-30%（陰跌尾）", "",
             t_tail.to_markdown(index=False), "",
             "## 結果三：連續outcome（中位數差＋Mann-Whitney U）", "",
             t_cont.to_markdown(index=False), "",
             "## 判讀", "",
             "- lift>=1.5：規則有增量訊號，保留",
             "- lift<1.5：砍走或重設門檻（Claude覆核建議）",
             "- 支持度過細（n<10）時lift不穩，只作參考",
             "",
             "## 本次實測結論（2026-09-18）", "",
             "1. **R1/R7 lift極高（42.9/11.3）但n=2**——兩案係規則設計來源，"
             "屬in-sample，lift只證明「機制運作」唔證明「前瞻預測力」",
             "2. **R4 lift=0.55（T+30尾）／0（crash）→ 已踢出alert_score**——"
             "貼20%折讓底喺呢個殼股市場係常規操作，唔係危險訊號",
             "3. **R8 lift≈1 → 已踢出alert_score**——低成交殼係呢個宇宙嘅"
             "背景條件（47%事件命中），冇區分力；日後可做乘數唔做加數",
             "4. **R2a/b/c支援度=0**——pct_source分流後得COMPUTED/無%",
             "（重解析證實：公告逐名%幾乎全部喺表格呈現，顯式句子regex抓唔到）。",
             "已命中者降級做R2_candidate（02113在列）。修法見KNOWN_ISSUES"
             "「逐名%表格抽取盲點」", "",
             "## 新評分制", "",
             "- alert_score = R1＋R2a＋R2b＋R2c＋R7（只計高lift觸發訊號）",
             "- 高度警示門檻由≥3改為**≥2**（每盞都係實訊號）",
             "- R4/R8保留布林欄做參考，唔入分",
             ""]
    out = ROOT / "rule_validation.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(t_crash.to_string(index=False), flush=True)
    print(t_tail.to_string(index=False), flush=True)
    print(f"→ {out}", flush=True)


if __name__ == "__main__":
    main()
