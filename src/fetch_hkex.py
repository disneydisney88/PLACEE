# -*- coding: utf-8 -*-
"""fetch_hkex.py — 承配人抽取批量驅動器（含斷點續傳）

用法：
  python src/fetch_hkex.py --probe          # 首批10宗驗證（含00254/02113）
  python src/fetch_hkex.py --limit 50       # 跑頭50宗未完成
  python src/fetch_hkex.py --codes 00254,02113
  python src/fetch_hkex.py --all            # 全部500宗（可斷點續傳）

輸出：data/placees.csv（逐event追加）；checkpoints/fetch_state.json
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
CKPT = ROOT / "checkpoints"
STATE_FILE = CKPT / "fetch_state.json"
PLACEES_CSV = DATA / "placees.csv"

COLUMNS = ['event_id', 'input_row', 'source_file', 'stock_code', 'stock_name',
           'ann_date', 'ann_type', 'mandate', 'placee_label', 'placee_name',
           'placee_type', 'beneficial_owner', 'shares', 'price', 'price_source',
           'pct_enlarged', 'below_5pct', 'lockup', 'independent_declared',
           'completion_date', 'source_url', 'snippet', 'parse_confidence',
           'fail_reason']

# 標題分類（規格3.2）
RE_PRIMARY = re.compile(r'認購新股份|認購事項|認購協議|配售新|配售事項|發行新股份|根據.*發行|配售.*股份|認購股份|代價股份')
RE_COMPLETION = re.compile(r'完成.*(認購|配售|發行)')
RE_SUPPLEMENT = re.compile(r'補充公告|補充公佈')
RE_EXCLUDE = re.compile(r'月報表|週報表|周報表|業績|中期報告|年度報告|環境、社會及管治|ESG|股東特別大會|股東週年大會|股東大會|董事名單|代表委任|通函|要約|購股權|年報|SFO|變動月報表')


def load_events() -> list[dict]:
    rows = []
    for fname, ann_type in [('配股事件20260831.csv', '配股'),
                            ('供股事件20260831.csv', '供股')]:
        p = DATA / 'input' / fname
        with open(p, encoding='utf-8-sig', newline='') as f:
            for i, r in enumerate(csv.DictReader(f)):
                code = re.match(r'(\d+)\.hk', r.get('代號', '') or '')
                if not code:
                    continue
                d = None
                md = re.match(r'(\d{2})/(\d{2})/(\d{2})', r.get('公佈日', '') or '')
                if md:
                    yy = int(md.group(3)) + (2000 if int(md.group(3)) < 70 else 1900)
                    try:
                        d = dt.date(yy, int(md.group(2)), int(md.group(1)))
                    except ValueError:
                        pass
                rows.append({
                    'event_id': f"{ann_type}_{r.get('代號','')}_{r.get('公佈日','')}",
                    'input_row': i + 2,
                    'source_file': fname,
                    'stock_code': code.group(1).zfill(5),
                    'stock_name': r.get('名稱', ''),
                    'ann_date': d,
                    'ann_type_input': r.get('配售方式', ''),
                    'mandate_input': (r.get('授權方式', '') or '').replace('普通授權', '一般授權'),
                    'price_input': (r.get('配股價 / 溢價(折讓)', '') or '').split('/')[0].strip(),
                    'agent_input': r.get('配售代理', ''),
                    'status_input': r.get('狀態', ''),
                    'completion_input': r.get('完成配售日期', ''),
                    'ann_type_group': ann_type,
                })
    return rows


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    tmp.replace(STATE_FILE)


def append_rows(rows: list[dict]) -> None:
    new_file = not PLACEES_CSV.exists()
    with open(PLACEES_CSV, 'a', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def select_pdfs(rows: list[dict]) -> dict:
    """由titleSearch結果挑 primary/completion/supplement。"""
    prim = comp = supp = None
    for r in rows:
        t = r['title']
        if RE_EXCLUDE.search(t):
            continue
        if comp is None and RE_COMPLETION.search(t):
            comp = r
            continue
        if RE_SUPPLEMENT.search(t):
            if supp is None:
                supp = r
            continue
        if prim is None and RE_PRIMARY.search(t):
            prim = r
    return {'primary': prim, 'completion': comp,
            'supplement': supp if prim is None else None}


def ann_date_from_row(r: dict) -> str | None:
    try:
        return dt.datetime.strptime(r['date'], '%d/%m/%Y').date().isoformat()
    except Exception:
        return None


def parse_mandate(title: str, text: str) -> str | None:
    if '特別授權' in title or '特別授權' in text[:3000]:
        return '特別授權'
    if '一般授權' in title or '普通授權' in title:
        return '一般授權'
    if '一般授權' in text[:3000]:
        return '一般授權'
    return None


def process_event(ev: dict, state: dict, dry: bool = False) -> list[dict]:
    """單宗事件 → placees row list（含event級失敗行）。"""
    code = ev['stock_code']
    out_fail = {
        'event_id': ev['event_id'], 'input_row': ev['input_row'],
        'source_file': ev['source_file'], 'stock_code': code,
        'stock_name': ev['stock_name'], 'ann_date': ev['ann_date'].isoformat()
        if ev['ann_date'] else None,
        'ann_type': ev['ann_type_input'] or ev['ann_type_group'],
        'mandate': ev['mandate_input'] or None,
    }
    if not ev['ann_date']:
        return [{**out_fail, 'fail_reason': 'BAD_INPUT_DATE'}]

    # 1) 搜尋公告（±3日；空手則±10日）
    sel = {'primary': None, 'completion': None, 'supplement': None}
    window_used = 3
    try:
        sid = hx.resolve_stock_id(code)
    except Exception as e:
        return [{**out_fail, 'fail_reason': f'STOCK_ID_FAIL: {e}'}]
    for w in (3, 10):
        d1 = (ev['ann_date'] - dt.timedelta(days=w)).strftime('%Y%m%d')
        d2 = (ev['ann_date'] + dt.timedelta(days=w)).strftime('%Y%m%d')
        try:
            rows = hx.search_titles(sid, d1, d2)
        except Exception as e:
            return [{**out_fail, 'fail_reason': f'SEARCH_FAIL: {e}'}]
        sel = select_pdfs(rows)
        window_used = w
        if sel['primary']:
            break

    if not any(sel.values()):
        return [{**out_fail, 'fail_reason': f'NO_ANN_FOUND(w={window_used})'}]

    # 2) 下載 + 解析
    parsed = {}
    for key in ('primary', 'supplement', 'completion'):
        r = sel.get(key)
        if not r:
            continue
        try:
            pdf = hx.download_pdf(r['pdf_url'])
        except Exception as e:
            parsed[key] = {'error': str(e), 'row': r}
            continue
        res = pd.parse_announcement(pdf)
        res['row'] = r
        res['pdf'] = str(pdf)
        parsed[key] = res

    src = parsed.get('primary') or parsed.get('supplement')
    if not src or src.get('error') or not src.get('text'):
        reason = 'PDF_FAIL: ' + str(src.get('error')) if src and src.get('error') else 'PDF_NO_TEXT'
        return [{**out_fail,
                 'source_url': sel['primary']['pdf_url'] if sel['primary'] else (
                     sel['supplement']['pdf_url'] if sel['supplement'] else None),
                 'fail_reason': reason}]

    text = src['text']
    main_row_info = src['row']
    conf = 'HIGH' if (not src['scanned'] and src['def_found'] and src['rows']) else (
        'LOW' if src['scanned'] else 'MED')

    # 事件層數值
    nums = src.get('event_numbers') or {}
    price = nums.get('price')
    price_source = 'announcement' if price else None
    if price is None:
        try:
            price = float(ev['price_input'])
            price_source = 'input_csv'
        except (ValueError, TypeError):
            price = None
    mandate = parse_mandate(main_row_info['title'], text) or ev['mandate_input'] or None

    completion_date = None
    comp = parsed.get('completion')
    if comp and not comp.get('error'):
        completion_date = (comp.get('event_numbers') or {}).get('completion_date_iso')
        if not completion_date:
            completion_date = ann_date_from_row(comp['row'])

    # 每placee股數（先主公告，後完成公告）
    def label_shares(label):
        s = pd.shares_for_label(text, label)
        if s:
            return s
        if comp and not comp.get('error'):
            return pd.shares_for_label(comp['text'], label)
        return None

    total_shares = nums.get('total_shares')
    if not total_shares and src['rows']:
        # 總股數 = 各placee之和（如果全部都搵到）
        ss = [label_shares(r['placee_label']) for r in src['rows']]
        if ss and all(ss):
            total_shares = sum(ss)

    agg_pct = None
    m = re.search(r'擴大後[^。\n]{0,60}?約?\s*([\d.]+)\s*%', text)
    if m:
        agg_pct = float(m.group(1))

    base = {**out_fail,
            'ann_type': ev['ann_type_input'] or
                        ('認購' if '認購' in main_row_info['title'] else
                         ('配售' if '配售' in main_row_info['title'] else ev['ann_type_group'])),
            'mandate': mandate,
            'lockup': nums.get('lockup', '未載'),
            'completion_date': completion_date,
            'source_url': main_row_info['pdf_url']}

    if not src['rows'] and not src.get('anon_rows'):
        return [{**base, 'price': price, 'price_source': price_source,
                 'parse_confidence': conf if conf != 'HIGH' else 'MED',
                 'fail_reason': 'NO_PLACEE_DEF'}]
    if not src['rows']:
        # 有「承配人/認購人」定義但屬泛稱冇具名（08245式）
        return [{**base, 'price': price, 'price_source': price_source,
                 'placee_label': src['anon_rows'][0]['placee_label'],
                 'parse_confidence': 'MED',
                 'fail_reason': 'NO_NAMED_PLACEE(泛稱定義冇具名)'}]

    rows_out = []
    for pr in src['rows']:
        sh = label_shares(pr['placee_label'])
        pct = None
        derived = False
        mpct = re.search(
            re.escape(pr['placee_label'].replace(' ', '')) +
            r'[^。\n]{0,200}?擴大後[^。\n]{0,60}?約?\s*([\d.]+)\s*%', text)
        if mpct:
            pct = float(mpct.group(1))
        elif sh and total_shares and agg_pct:
            pct = round(agg_pct * sh / total_shares, 2)
            derived = True
        below5 = (None if pct is None else (pct < 5.0))
        snip = pd.snippet_from(text, pr['placee_name']) if pr['placee_name'] else ''
        rows_out.append({**base,
                         'placee_label': pr['placee_label'],
                         'placee_name': pr['placee_name'],
                         'placee_type': pr['placee_type'],
                         'beneficial_owner': pr['beneficial_owner'],
                         'shares': sh, 'price': price, 'price_source': price_source,
                         'pct_enlarged': pct, 'below_5pct': below5,
                         'independent_declared': pr['independent_declared'],
                         'snippet': snip,
                         'parse_confidence': 'MED' if (derived or not sh) else conf,
                         'fail_reason': None})
    return rows_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--offset', type=int, default=0)
    ap.add_argument('--codes', type=str, default='')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    events = load_events()
    state = load_state()
    if args.codes:
        want = {c.strip().zfill(5) for c in args.codes.split(',')}
        events = [e for e in events if e['stock_code'] in want]
    if args.probe:
        # 首批：包含已知答案00254（CSV內）及02113（唔喺CSV，spec指明之個案）
        events = events[:8]
        extra = [e for e in load_events() if e['stock_code'] == '00254']
        extra.append({
            'event_id': 'MANUAL_02113_02/09/26', 'input_row': None,
            'source_file': 'MANUAL_SPEC（規格書指明個案；02113認購公告2026-09-02）',
            'stock_code': '02113', 'stock_name': '世紀集團國際',
            'ann_date': dt.date(2026, 9, 2), 'ann_type_input': '新股',
            'mandate_input': '一般授權', 'price_input': '',
            'agent_input': '', 'status_input': '', 'completion_input': '',
            'ann_type_group': '配股'})
        seen = {e['event_id'] for e in extra}
        events = extra + [e for e in events if e['event_id'] not in seen]
        events = events[:12]
    elif args.offset:
        events = events[args.offset:]
    if not args.all:
        done = {k for k, v in state.items() if v.get('status') == 'done'}
        events = [e for e in events if e['event_id'] not in done]
        if args.limit:
            events = events[:args.limit]

    print(f"待處理 {len(events)} 宗", flush=True)
    n_ok = n_rows = 0
    for i, ev in enumerate(events):
        try:
            rows = process_event(ev, state, dry=args.dry)
            status = 'done'
        except Exception as e:
            rows = [{'event_id': ev['event_id'], 'input_row': ev['input_row'],
                     'source_file': ev['source_file'],
                     'stock_code': ev['stock_code'],
                     'stock_name': ev['stock_name'],
                     'fail_reason': f'EXC: {type(e).__name__}: {e}'}]
            status = 'error'
        state[ev['event_id']] = {
            'status': status, 'n_rows': len(rows),
            'fail': rows[0].get('fail_reason') if len(rows) == 1 else None}
        if not args.dry:
            append_rows(rows)
            save_state(state)
        names = [r.get('placee_name') for r in rows if r.get('placee_name')]
        n_ok += 1 if names else 0
        n_rows += len(rows)
        summary = ','.join(names[:6]) if names else str(rows[0].get('fail_reason'))
        print(f"[{i+1}/{len(events)}] {ev['stock_code']} {ev['stock_name']}"
              f" -> {len(rows)}行 {summary}", flush=True)
    print(f"完成：{n_ok}/{len(events)} 宗有承配人，共{n_rows}行", flush=True)


if __name__ == '__main__':
    main()
