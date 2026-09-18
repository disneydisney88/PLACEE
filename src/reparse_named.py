# -*- coding: utf-8 -*-
"""reparse_named.py — 對全部「有具名承配人」事件重跑解析，補 pct_enlarged_source

背景（Claude覆核①）：pct_enlarged有EXPLICIT（公告逐名列%）與COMPUTED
（總%×個股/總股數推算）兩種來源；R2系列規則只應食EXPLICIT。
PDF已入cache，只重搜標題（HKEX ~2請求/宗），重寫placees.csv該批事件行。
"""
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import fetch_hkex as fh    # noqa: E402

DATA = ROOT / "data"


def main():
    events = {e['event_id']: e for e in fh.load_events()}
    pl_path = DATA / 'placees.csv'
    pl = pd.read_csv(pl_path, dtype={'stock_code': str}, encoding='utf-8-sig')
    named_ids = sorted(set(pl.loc[pl['placee_name'].notna()
                                  & (pl['placee_name'] != ''), 'event_id']))
    print(f"具名承配人事件: {len(named_ids)}", flush=True)

    new_rows = []
    n_done = 0
    for i, eid in enumerate(named_ids):
        ev = events.get(eid)
        if ev is None:
            print(f"[{i+1}] {eid} 唔喺輸入清單，跳過", flush=True)
            continue
        try:
            rows = fh.process_event(ev, {}, dry=False)
        except Exception as e:
            print(f"[{i+1}] {ev['stock_code']} EXC {e}", flush=True)
            continue
        for r in rows:
            r['event_id'] = eid
            if r.get('placee_name'):
                new_rows.append(r)
        n_done += 1
        names = [r.get('placee_name') for r in rows if r.get('placee_name')]
        print(f"[{i+1}/{len(named_ids)}] {ev['stock_code']} -> "
              f"{len(names)}名 {','.join(names[:4])}", flush=True)

    old = pl[~pl['event_id'].isin({r['event_id'] for r in new_rows})]
    out = pd.concat([old, pd.DataFrame(new_rows)], ignore_index=True)
    # 欄位排序對齊舊檔＋新欄
    cols = [c for c in pl.columns if c in out.columns] + \
           [c for c in out.columns if c not in pl.columns]
    out = out[cols]
    out.to_csv(pl_path, index=False, encoding='utf-8-sig')
    src_dist = out['pct_enlarged_source'].value_counts(dropna=False).to_dict() \
        if 'pct_enlarged_source' in out.columns else {}
    print(f"重寫{n_done}宗事件、{len(new_rows)}行；pct_source分佈：{src_dist}",
          flush=True)


if __name__ == '__main__':
    main()
