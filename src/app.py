# -*- coding: utf-8 -*-
"""app.py — hk-placee-registry 查詢介面（規格§七）

運行：  streamlit run src/app.py

設計要求（規格）：所有數字旁必須可點開 source_url；冇來源嘅數字唔好顯示。
頁面：①姓名搜尋 ②券商搜尋 ③亮燈榜 ④個案詳情
"""
import pathlib
import sys

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

st.set_page_config(page_title="承配人索引庫 hk-placee-registry",
                   page_icon="🔎", layout="wide")


@st.cache_data(ttl="10m")
def load_placees() -> pd.DataFrame:
    return pd.read_csv(DATA / "placees.csv", dtype={"stock_code": str},
                       encoding="utf-8-sig")


@st.cache_data(ttl="10m")
def load_alerts() -> pd.DataFrame:
    return pd.read_csv(DATA / "alerts.csv", dtype={"stock_code": str},
                       encoding="utf-8-sig")


@st.cache_data(ttl="10m")
def load_flags() -> pd.DataFrame:
    try:
        return pd.read_csv(DATA / "warehouse_flags.csv", dtype={"stock_code": str},
                           encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl="10m")
def load_outcomes() -> pd.DataFrame:
    try:
        return pd.read_csv(DATA / "outcomes.csv", dtype={"stock_code": str},
                           encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl="10m")
def load_repeat() -> pd.DataFrame:
    try:
        return pd.read_csv(DATA / "repeat_placees.csv", encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl="10m")
def load_daily(code: str) -> pd.DataFrame:
    path = ROOT / "cache" / "ccass" / "ccass_daily.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"code": str, "participant_id": str})
    return df[df["code"] == code]


@st.cache_data(ttl="10m")
def load_prices(code: str) -> pd.DataFrame:
    base = ROOT / "cache" / "hk_prices_master.csv"
    if not base.exists():
        return pd.DataFrame()
    with open(base, encoding="utf-8-sig") as f:
        df = pd.read_csv(f, dtype={"code": str}, on_bad_lines="warn")
    df = df[df["code"] == code]
    bf = ROOT / "cache" / "price_backfill.csv"
    if bf.exists():
        with open(bf, encoding="utf-8-sig") as f:
            df2 = pd.read_csv(f, dtype={"code": str})
        df2 = df2[df2["code"] == code]
        df = pd.concat([df, df2], ignore_index=True).drop_duplicates(
            subset=["date"], keep="last")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date")


def show_placee_table(df: pd.DataFrame):
    """承配人行表：數字帶source_url連結（規格要求）。"""
    if df.empty:
        st.info("冇結果。")
        return
    show = df.copy()
    show["source"] = show["source_url"].fillna("").apply(
        lambda u: "🔗公告" if isinstance(u, str) and u.startswith("http") else "")
    cols = {
        "stock_code": st.column_config.TextColumn("代號"),
        "stock_name": st.column_config.TextColumn("股票"),
        "ann_date": st.column_config.TextColumn("公告日"),
        "ann_type": st.column_config.TextColumn("類型"),
        "mandate": st.column_config.TextColumn("授權"),
        "placee_label": st.column_config.TextColumn("標籤"),
        "placee_name": st.column_config.TextColumn("承配人"),
        "placee_type": st.column_config.TextColumn("類別"),
        "beneficial_owner": st.column_config.TextColumn("實益擁有人"),
        "shares": st.column_config.NumberColumn("股數", format="%d"),
        "price": st.column_config.NumberColumn("認購價", format="%.3f"),
        "pct_enlarged": st.column_config.NumberColumn("擴大後%", format="%.2f"),
        "below_5pct": st.column_config.CheckboxColumn("<5%"),
        "lockup": st.column_config.TextColumn("禁售"),
        "completion_date": st.column_config.TextColumn("完成日"),
        "parse_confidence": st.column_config.TextColumn("置信"),
        "source": st.column_config.LinkColumn("來源", display_text="🔗公告"),
        "snippet": None, "source_url": None, "case_tag": None,
    }
    cols = {k: v for k, v in cols.items() if k in show.columns or v is None}
    st.dataframe(show, column_config=cols, hide_index=True, height=460)


def export_section(df: pd.DataFrame, key: str):
    with st.container(horizontal=True):
        st.download_button("下載CSV", df.to_csv(index=False, encoding="utf-8-sig"),
                           file_name=f"{key}.csv", mime="text/csv",
                           disabled=df.empty)
        md = df.to_markdown(index=False) if not df.empty else ""
        st.download_button("下載Markdown", md, file_name=f"{key}.md",
                           mime="text/markdown", disabled=df.empty)


# ---------------------------------------------------------------- 頁面

def page_name():
    st.title("🔎 姓名搜尋")
    st.caption("由承配人姓名反查全部歷史個案（同名只係候選，唔代表同一人）")
    placees = load_placees()
    names = (placees["placee_name"].dropna().sort_values().unique().tolist())
    q = st.text_input("姓名（支援部分匹配）", key="name_q",
                      placeholder="例：付尚輝")
    pick = st.selectbox("…或者直接揀", [""] + names,
                        format_func=lambda x: x or "—")
    df = placees[placees["placee_name"].notna()]
    if q:
        df = df[df["placee_name"].str.contains(q, regex=False, na=False)]
    elif pick:
        df = df[df["placee_name"] == pick]
    st.write(f"**{len(df)}行** 承配人記錄")
    show_placee_table(df)
    export_section(df, "name_search")
    if not df.empty:
        st.subheader("同名跨股（候選）")
        rep = load_repeat()
        if q:
            rep = rep[rep["placee_name"].str.contains(q, regex=False, na=False)]
        elif pick:
            rep = rep[rep["placee_name"] == pick]
        st.dataframe(rep, hide_index=True)
        with st.expander("原文片段（snippet）"):
            for _, r in df.head(30).iterrows():
                st.markdown(
                    f"**{r['stock_code']} {r['stock_name']}** {r['ann_date']} "
                    f"· {r['placee_label']} · "
                    f"[source]({r['source_url']})" if isinstance(r["source_url"], str) else "")
                st.text(r["snippet"])


def page_broker():
    st.title("🏦 券商搜尋")
    st.caption("由CCASS衛星倉偵測結果反查個案（散戶白名單=富途/耀才/盈立/老虎/微牛/致富/長橋/輝立/盈透/華盛）")
    flags = load_flags()
    if flags.empty:
        st.warning("warehouse_flags.csv 未有數據（先跑 src/fetch_ccass.py + detect_warehouse.py）")
        return
    brokers = sorted(flags["broker_id"].unique().tolist())
    pick = st.selectbox("券商 CCASS ID", brokers)
    sub = flags[flags["broker_id"] == pick]
    st.write(f"**{len(sub)}** 個flag")
    st.dataframe(sub, hide_index=True)
    export_section(sub, "broker_flags")


def page_alerts():
    st.title("🚨 亮燈榜")
    st.caption("R1寶新+粵商國際｜R2多名個人均等<5%｜R4貼20%折讓底｜R7衛星倉派貨｜R8低成交殼｜R3/R5/R6/R9=NOT_TESTED(需DI/逐筆)")
    alerts = load_alerts()
    c1, c2, c3 = st.columns(3)
    with c1:
        min_score = st.slider("最少alert_score", 0, 5, 0)
    with c2:
        years = sorted({str(a)[:4] for a in alerts["ann_date"].dropna()})
        year = st.selectbox("年份", ["全部"] + years)
    with c3:
        mandates = ["全部"] + sorted(alerts["mandate"].dropna().unique().tolist())
        mandate = st.selectbox("授權方式", mandates)
    df = alerts[alerts["alert_score"] >= min_score]
    if year != "全部":
        df = df[df["ann_date"].astype(str).str.startswith(year)]
    if mandate != "全部":
        df = df[df["mandate"] == mandate]
    st.write(f"**{len(df)}** 事件；高度警示(≥3)共 "
             f"**{int((alerts['alert_score'] >= 3).sum())}**")
    st.dataframe(df, hide_index=True, height=520)
    export_section(df, "alerts")


def page_case():
    st.title("📁 個案詳情")
    placees = load_placees()
    events = (placees[placees["ann_date"].notna()]
              .groupby(["stock_code", "stock_name", "ann_date"], as_index=False)
              .first()
              .sort_values("ann_date", ascending=False))
    pick = st.selectbox(
        "個案", events.itertuples(index=False),
        format_func=lambda t: f"{t.stock_code} {t.stock_name} @ {t.ann_date}")
    code, ann = pick.stock_code, pick.ann_date
    sub = placees[(placees["stock_code"] == code)
                  & (placees["ann_date"] == ann)]
    st.subheader(f"{code} {pick.stock_name}")
    show_placee_table(sub)
    export_section(sub, f"case_{code}_{ann}")

    outcomes = load_outcomes()
    o = outcomes[(outcomes["stock_code"] == code)
                 & (outcomes["ann_date"] == ann)]
    if not o.empty:
        st.subheader("結局標註")
        r = o.iloc[0]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("公告價基準", r.get("price_base"))
        m2.metric("T+30", r.get("ret_ann_30"))
        m3.metric("T+60", r.get("ret_ann_60"))
        m4.metric("T+90", r.get("ret_ann_90"))
        m5.metric("90日最大回撤", r.get("max_drawdown_90"))
        st.caption(f"價格來源：{r.get('price_source')}｜crash={r.get('crash_flag')} "
                   f"@{r.get('crash_date')}｜成交爆量倍數={r.get('vol_spike_ratio')}")

    daily = load_daily(code)
    if not daily.empty:
        st.subheader("CCASS 券商持股%（事件視窗）")
        p = daily.pivot_table(index="date", columns="participant_id",
                              values="pct", aggfunc="last").ffill()
        top = p.max().sort_values(ascending=False).head(12).index.tolist()
        chart_df = p[top]
        st.line_chart(chart_df,
                      x_label="日期", y_label="持股%")
        st.caption(f"僅顯示持股%最高12名券商；日曆截止 {daily['date'].max()}")

    prices = load_prices(code)
    if not prices.empty:
        st.subheader("收市價（未調整）")
        st.line_chart(prices.set_index("date")["close"], x_label="日期",
                      y_label="收市價(HKD)")
        st.caption("⚠️ 合股/拆股前價格未在此圖調整（結局欄已用adj_close校正）")

    with st.expander("原文片段＋來源"):
        for _, r in sub.iterrows():
            url = r.get("source_url")
            st.markdown(f"**{r['placee_label']} → {r['placee_name']}** · "
                        f"[{'公告原文' if isinstance(url, str) and url.startswith('http') else '無來源'}]({url})")
            st.text(r.get("snippet", ""))


pages = {
    "姓名搜尋": page_name,
    "券商搜尋": page_broker,
    "亮燈榜": page_alerts,
    "個案詳情": page_case,
}
st.sidebar.title("hk-placee-registry")
st.sidebar.caption("承配人索引庫＋亮燈引擎\n\n學術研究用途；所有數字可追溯至HKEX公告")
choice = st.sidebar.radio("頁面", list(pages.keys()), label_visibility="collapsed")
pages[choice]()
