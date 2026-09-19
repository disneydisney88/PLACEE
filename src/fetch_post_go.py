# -*- coding: utf-8 -*-
"""fetch_post_go.py — [P6] GO後承配人專項（Claude排優先：全市場抓取之前）

邏輯：
1. 讀 全購事件20260831.csv → 每隻股 GO完成日T（最後接納；未公佈則用公佈日期）
2. titleSearch T .. T+24個月，標題含：配售/認購/Placing/Subscription/
   特別授權/Specific Mandate/補償安排（含完成公告）
3. 逐份PDF跑現有抽取（釋義+數值），承配人行加：go_ref、months_after_go、
   superseded（同一隻股以最遲具名公告為最終名單，較早者superseded=1）
4. 輸出 data/post_go_placees.csv（斷點續傳：checkpoints/post_go_state.json）

硬測試目標：08106 六名承配人（WOO POH SUN/粵港澳民營投資/GAO JIANLONG/
黃國良/劉朝暉/范惠深），/registry/name?q=劉朝暉 命中。
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import hkex_client as hx          # noqa: E402
import parse_definitions as pd    # noqa: E402

DATA = ROOT / "data"
STATE = ROOT / "checkpoints" / "post_go_state.json"
OUT = DATA / "post_go_placees.csv"

RE_POST = re.compile(r'配售|認購|Placing|Subscription|特別授權|Specific Mandate|補償安排', re.I)
RE_EXCLUDE = re.compile(
    r'月報表|週報表|業績|中期報告|年度報告|環境、社會|ESG|股東特別大會|股東週年大會|'
    r'股東大會|董事名單|代表委任|通函|年報|購股權|要約人|綜合文件|接納表格|'
    r'回應文件|要約期|標準比率')
COLUMNS = ['go_ref', 'go_name', 'months_after_go', 'superseded', 'ann_title',
           'event_id', 'input_row', 'source_file', 'stock_code', 'stock_name',
           'ann_date', 'ann_type', 'mandate', 'placee_label', 'placee_name',
           'placee_type', 'beneficial_owner', 'shares', 'price', 'price_source',
           'pct_enlarged', 'pct_enlarged_source', 'below_5pct', 'lockup',
           'independent_declared', 'completion_date', 'source_url', 'snippet',
           'parse_confidence', 'fail_reason']


def load_go_events() -> list[dict]:
    out = []
    with open(DATA / 'input' / '全購事件20260831.csv', encoding='utf-8-sig', newline='') as f:
        for i, r in enumerate(csv.DictReader(f)):
            m = re.match(r'(\d+)\.hk', r.get('代號', '') or '')
            if not m:
                continue
            def pdate(s):
                mm = re.match(r'(\d{2})/(\d{2})/(\d{2})', s or '')
                if not mm:
                    return None
                yy = int(mm.group(3)) + (2000 if int(mm.group(3)) < 70 else 1900)
                try:
                    return dt.date(yy, int(mm.group(2)), int(mm.group(1)))
                except ValueError:
                    return None
            ann = pdate(r.get('公佈日期', ''))
            final_acc = pdate(r.get('最後接納', ''))
            t_date = final_acc or ann
            if not t_date:
                continue
            out.append({
                'go_ref': f"GO_{m.group(1)}_{r.get('公佈日期', '')}",
                'stock_code': m.group(1).zfill(5),
                'stock_name': r.get('名稱', ''),
                'go_name': r.get('新主', ''),
                't_date': t_date,
                'status': r.get('狀態', ''),
                'input_row': i + 2,
            })
    return out


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    return {}


def save_state(st: dict) -> None:
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
    tmp.replace(STATE)


def append_rows(rows: list[dict]) -> None:
    new = not OUT.exists()
    with open(OUT, 'a', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def months_between(a: dt.date, b: dt.date) -> float:
    return round((b - a).days / 30.44, 1)


def search_announcements(code: str, t_date: dt.date) -> list[dict]:
    """T..T+24個月，分年度窗搜尋＋標題過濾。"""
    sid = hx.resolve_stock_id(code)
    seen = {}
    spans = [(t_date, t_date + dt.timedelta(days=365)),
             (t_date + dt.timedelta(days=366), t_date + dt.timedelta(days=730))]
    for d1, d2 in spans:
        rows = hx.search_titles(sid, d1.strftime('%Y%m%d'), d2.strftime('%Y%m%d'))
        for r in rows:
            if r['file'] and r['title'] and r['file'] not in seen:
                seen[r['file']] = r
    out = []
    for r in seen.values():
        if RE_EXCLUDE.search(r['title']):
            continue
        if RE_POST.search(r['title']):
            out.append(r)
    return out


def parse_ann(pdf_path: pathlib.Path, ev: dict, row: dict) -> list[dict]:
    res = pd.parse_announcement(pdf_path)
    ann_date = None
    md = re.match(r'(\d{2})/(\d{2})/(\d{4})', row['date'])
    if md:
        ann_date = dt.date(int(md.group(3)), int(md.group(2)), int(md.group(1)))
    base = {
        'go_ref': ev['go_ref'], 'go_name': ev['go_name'],
        'months_after_go': months_between(ev['t_date'], ann_date) if ann_date else None,
        'superseded': None,
        'ann_title': row['title'][:120],
        'event_id': f"PGO_{ev['stock_code']}_{row['date']}",
        'input_row': ev['input_row'], 'source_file': '全購事件20260831.csv',
        'stock_code': ev['stock_code'], 'stock_name': ev['stock_name'],
        'ann_date': ann_date.isoformat() if ann_date else None,
        'ann_type': '認購' if '認購' in row['title'] else (
            '配售' if '配售' in row['title'] else row['title'][:20]),
        'completion_date': (res.get('event_numbers') or {}).get('completion_date_iso'),
    }
    out = []
    named = res.get('rows') or []
    for pr in named:
        snip = pd.snippet_from(res['text'], pr['placee_name']) if pr['placee_name'] else ''
        out.append({**base, 'placee_label': pr['placee_label'],
                    'placee_name': pr['placee_name'],
                    'placee_type': pr['placee_type'],
                    'beneficial_owner': pr['beneficial_owner'],
                    'independent_declared': pr['independent_declared'],
                    'source_url': row['pdf_url'], 'snippet': snip,
                    'fail_reason': None})
    if not named:
        anon = (res.get('anon_rows') or [{}])[0]
        out.append({**base, 'placee_label': anon.get('placee_label'),
                    'placee_name': None, 'placee_type': None,
                    'source_url': row['pdf_url'], 'snippet': '',
                    'parse_confidence': 'MED' if res['def_found'] else (
                        'LOW' if res['scanned'] else None),
                    'fail_reason': ('NO_NAMED_PLACEE' if res['def_found']
                                    else ('PDF_NO_TEXT' if res['scanned']
                                          else 'NO_PLACEE_DEF'))})
    return out


def process(ev: dict, st: dict) -> list[dict]:
    key = ev['go_ref']
    if st.get(key, {}).get('status') == 'done':
        return []
    try:
        anns = search_announcements(ev['stock_code'], ev['t_date'])
    except Exception as e:
        st[key] = {'status': 'search_fail', 'err': str(e)[:120]}
        save_state(st)
        return []
    all_rows = []
    for row in anns[:6]:  # 每GO最多6份，夠覆蓋初次/補充/完成
        try:
            pdf = hx.download_pdf(row['pdf_url'])
        except Exception as e:
            all_rows.append({'go_ref': ev['go_ref'], 'ann_title': row['title'][:80],
                             'ann_date': None, 'event_id': f"PGO_{ev['stock_code']}_{row['date']}",
                             'stock_code': ev['stock_code'], 'stock_name': ev['stock_name'],
                             'source_url': row['pdf_url'],
                             'fail_reason': f'PDF_FAIL:{str(e)[:60]}'})
            continue
        all_rows.extend(parse_ann(pdf, ev, row))
    # superseded：同一隻股，最遲「有具名」嘅公告=0，較早具名公告=1
    dated = [r for r in all_rows if r.get('placee_name') and r.get('ann_date')]
    if dated:
        latest = max(r['ann_date'] for r in dated)
        latest_eid = {r['event_id'] for r in dated if r['ann_date'] == latest}
        for r in all_rows:
            if r.get('placee_name'):
                r['superseded'] = 0 if r['event_id'] in latest_eid else 1
    # 替代偵測：「新認購人三」句式（WU LAN退出、GAO JIANLONG頂上案例）
    # 每份公告text搵 新(認購人|承配人|投資者)X + 鄰近姓名 → 新row；
    # 同號原label行 superseded=1
    cn = '一二三四五六七八九十'
    for row in anns:
        try:
            pdf = hx.download_pdf(row['pdf_url'])
        except Exception:
            continue
        text, _ = pd.extract_text(pdf)
        for m in re.finditer(
                r'新(?:認購人|承配人|投資者|認購方)([一二三四五六七八九十]+|[A-Z])', text):
            lab_new = f"新認購人{m.group(1)}"
            seg = ''
            # 首選緊貼結構：與{姓名}（「新認購人X」）訂立
            name = None
            tight = re.search(
                r'(?:與|和|同)\s*([^，。；\n]{2,60}?)\s*（「?新(?:認購人|承配人|投資者|認購方)'
                + re.escape(m.group(1)) + r'」?）', text)
            if tight:
                name = tight.group(1).strip()
                mp = (pd.RE_PERSON_ROMAN.search(name) or pd.RE_PERSON.search(name))
                if mp:
                    g1 = re.sub(r'\s+', ' ', mp.group(1)).strip()
                    name = f"{g1}{mp.group(2)}"
            else:
                seg = text[max(0, m.start() - 400):m.end() + 400]
                mp = pd.RE_PERSON_ROMAN.search(seg) or pd.RE_PERSON.search(seg)
                if mp:
                    g1 = re.sub(r'\s+', ' ', mp.group(1)).strip()
                    name = f"{g1}{mp.group(2)}"
                else:
                    me = pd.RE_ENTITY.search(seg) or pd.RE_CN_ENTITY.search(seg)
                    if me:
                        name = re.sub(r'\s+', ' ', me.group(1)).strip().rstrip('，,')
            if not name:
                continue
            orig_lab = f"認購人{m.group(1)}"
            md2 = re.match(r'(\d{2})/(\d{2})/(\d{4})', row['date'])
            ann_iso = (dt.date(int(md2.group(3)), int(md2.group(2)),
                               int(md2.group(1))).isoformat() if md2 else None)
            for r in all_rows:
                lab_stripped = str(r.get('placee_label', '')).replace(' ', '')
                if (r.get('ann_date') and ann_iso
                        and r['ann_date'] < ann_iso
                        and lab_stripped.startswith(orig_lab)):
                    r['superseded'] = 1
            all_rows.append({
                'go_ref': ev['go_ref'], 'go_name': ev['go_name'],
                'months_after_go': None, 'superseded': 0,
                'ann_title': row['title'][:120],
                'event_id': f"PGO_{ev['stock_code']}_{row['date']}_{lab_new}",
                'input_row': ev['input_row'], 'source_file': '全購事件20260831.csv',
                'stock_code': ev['stock_code'], 'stock_name': ev['stock_name'],
                'ann_date': None, 'ann_type': '認購(替代)',
                'placee_label': lab_new, 'placee_name': name,
                'placee_type': '個人' if re.search(r'先生|女士', name) else (
                    '公司' if re.search(r'有限公司|LIMITED|LTD', name, re.I) else 'UNKNOWN'),
                'beneficial_owner': None, 'shares': None, 'price': None,
                'price_source': None, 'pct_enlarged': None,
                'pct_enlarged_source': None, 'below_5pct': None, 'lockup': None,
                'independent_declared': None,
                'completion_date': (all_rows[0].get('completion_date')
                                    if all_rows else None),
                'source_url': row['pdf_url'],
                'snippet': re.sub(r'\s+', ' ', seg[:200]),
                'parse_confidence': 'MED', 'fail_reason': None,
            })
            break  # 每份公告每個label只報一次
    st[key] = {'status': 'done', 'n_anns': len(anns), 'n_rows': len(all_rows)}
    save_state(st)
    return all_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes', default='')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    events = load_go_events()
    if args.codes:
        want = {c.strip().zfill(5) for c in args.codes.split(',')}
        events = [e for e in events if e['stock_code'] in want]
    st = load_state()
    todo = [e for e in events if st.get(e['go_ref'], {}).get('status') != 'done']
    if args.limit:
        todo = todo[:args.limit]
    print(f"GO事件總數 {len(events)}，待處理 {len(todo)}", flush=True)
    n_named = 0
    for i, ev in enumerate(todo):
        rows = process(ev, st)
        if rows:
            append_rows(rows)
        names = [r.get('placee_name') for r in rows if r.get('placee_name')]
        n_named += 1 if names else 0
        print(f"[{i+1}/{len(todo)}] {ev['stock_code']} {ev['stock_name'][:10]}"
              f" T={ev['t_date']} -> {len(rows)}行 "
              + (','.join(names[:6]) if names else
                 (rows[0].get('fail_reason') if rows else 'done-skip')), flush=True)
    print(f"完成：{n_named}/{len(todo)} GO事件有具名承配人", flush=True)


if __name__ == '__main__':
    main()
