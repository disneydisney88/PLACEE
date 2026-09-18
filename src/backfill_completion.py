# -*- coding: utf-8 -*-
"""backfill_completion.py — 補完成日期（完成公告PDF→completion_date_iso）

背景：批量首跑時 extract_event_numbers 對完成公告冇釋義段提早return（已修），
本腳本只針對「狀態=已完成」事件：搜尋窗口內完成公告（多數已入cache），
抽完成日期，回寫 placees.csv（全部同event行）。

fallback：公告抽唔到日子 → 用輸入CSV嘅完成配售日期（source=input_csv）。
"""
import csv
import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import hkex_client as hx           # noqa: E402
import parse_definitions as pd     # noqa: E402
from fetch_hkex import load_events, select_pdfs, ann_date_from_row  # noqa: E402

DATA = ROOT / "data"


def main():
    events = [e for e in load_events()
              if '完成' in (e.get('status_input') or '')]
    print(f"已完成狀態事件: {len(events)}", flush=True)
    input_comp = {e['event_id']: e.get('completion_input', '') for e in load_events()}
    comp_map = {}
    for i, ev in enumerate(events):
        code = ev['stock_code']
        try:
            sid = hx.resolve_stock_id(code)
            rows = hx.search_titles(sid,
                                    (ev['ann_date'] - dt.timedelta(days=10)).strftime('%Y%m%d'),
                                    (ev['ann_date'] + dt.timedelta(days=60)).strftime('%Y%m%d'))
        except Exception as e:
            comp_map[ev['event_id']] = (None, f'search_fail:{e}')
            continue
        sel = select_pdfs(rows)
        comp = sel.get('completion')
        iso = None
        if comp:
            try:
                pdf = hx.download_pdf(comp['pdf_url'])
                res = pd.parse_announcement(pdf)
                iso = (res.get('event_numbers') or {}).get('completion_date_iso')
            except Exception:
                iso = None
            if not iso:
                iso = ann_date_from_row(comp)  # fallback:完成公告發布日
        src = 'announcement' if comp else None
        comp_map[ev['event_id']] = (iso, src)
        if (i + 1) % 50 == 0:
            print(f"[{i+1}/{len(events)}]", flush=True)

    # 回寫 placees.csv：公告來源優先於輸入CSV來源
    import pandas as pd
    pl_path = DATA / 'placees.csv'
    pl = pd.read_csv(pl_path, dtype={'stock_code': str}, encoding='utf-8-sig')
    if 'completion_date_source' not in pl.columns:
        pl['completion_date_source'] = None
    completed_ids = {e['event_id'] for e in events}
    # 重置呢批事件嘅舊值（上次用修復前代碼跑，全部跌咗入input_csv兜底）
    mask_reset = pl['event_id'].isin(completed_ids)
    pl.loc[mask_reset, 'completion_date'] = None
    pl.loc[mask_reset, 'completion_date_source'] = None
    n_ann = n_input = 0
    for idx, r in pl.iterrows():
        if pd.notna(r.get('completion_date')):
            continue  # 已有（非完成狀態事件或其他來源）
        iso, src = comp_map.get(r['event_id'], (None, None))
        if not iso:
            # fallback: 輸入CSV完成配售日期（DD/MM/YY）
            m = re.match(r'(\d{2})/(\d{2})/(\d{2})',
                         str(input_comp.get(r['event_id'], '') or ''))
            if m:
                yy = int(m.group(3)) + (2000 if int(m.group(3)) < 70 else 1900)
                try:
                    iso = dt.date(yy, int(m.group(2)), int(m.group(1))).isoformat()
                    src = 'input_csv'
                except ValueError:
                    iso = None
        if iso:
            pl.at[idx, 'completion_date'] = iso
            pl.at[idx, 'completion_date_source'] = src
            if src == 'announcement':
                n_ann += 1
            else:
                n_input += 1
    pl.to_csv(pl_path, index=False, encoding='utf-8-sig')
    print(f"補完成日期：公告來源{n_ann}行、輸入CSV來源{n_input}行", flush=True)


if __name__ == '__main__':
    main()
