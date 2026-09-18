# -*- coding: utf-8 -*-
"""parse_definitions.py — 公告「釋義」段落承配人解析器

設計原則（規格紀律1/2）：
- 只認原文，唔推測。抽唔到 → NULL / UNKNOWN + fail_reason
- 每個輸出欄位可追溯到 snippet（<=200字）

主要入口：
  extract_text(pdf_path) -> (text, engine)          # pdftotext -layout 優先
  parse_announcement(pdf_path) -> dict              # 結構化輸出（單一公告）
"""
import pathlib
import re
import subprocess

# ---------------------------------------------------------------- 文字抽取

RE_MOJIBAKE = re.compile(r'[\u0700-\u0DFF\u0E00-\u0FFF\u1780-\u17FF\u202a-\u202e\u2066-\u2069\uFFF0-\uFFFF]')


def _score(t: str) -> int:
    """中文公告文字質素分：CJK越多越好，亂碼區字元重罰。"""
    if not t:
        return 0
    cjk = len(re.findall(r'[\u4e00-\u9fff]', t))
    weird = len(RE_MOJIBAKE.findall(t))
    return cjk - 3 * weird


def _pdfplumber_text(pdf_path: pathlib.Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            return "\n".join((p.extract_text() or '') for p in pdf.pages)
    except Exception:
        return ''


def extract_text(pdf_path: pathlib.Path) -> tuple[str, str]:
    """pdftotext -layout 優先；偵測到亂碼/近乎空白則 pdfplumber 後備。"""
    txt_out = pdf_path.with_suffix(".txt")
    best, best_engine = '', 'none'
    try:
        subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), str(txt_out)],
            check=True, capture_output=True, timeout=120)
        t = txt_out.read_text(encoding="utf-8", errors="replace")
        if len(t.strip()) >= 100:
            best, best_engine = t, "pdftotext"
    except Exception:
        pass
    # 亂碼或低質 → pdfplumber
    if _score(best) <= 0 or (best and len(RE_MOJIBAKE.findall(best)) > len(best) * 0.005):
        t2 = _pdfplumber_text(pdf_path)
        if _score(t2) > _score(best):
            best, best_engine = t2, "pdfplumber"
    return best, best_engine


def is_scanned(text: str, n_pages_hint: int = 0) -> bool:
    """文字層近乎空白 → 掃描圖。按每頁<120字元估算。"""
    plain = re.sub(r"\s", "", text)
    if n_pages_hint and len(plain) / max(n_pages_hint, 1) < 120:
        return True
    return len(plain) < 120

# ---------------------------------------------------------------- 基礎 regex

RE_DEF_LINE = re.compile(
    r'[「『]\s*(?P<label>[^」』]{1,20}?)\s*[」』]\s*(?:指|means)\s*(?P<body>.*)$')
RE_NEWDEF = re.compile(r'[「『]\s*[^」』]{1,20}?\s*[」』]')
RE_PAGE_NO = re.compile(r'^\s*[-–—\d]{1,4}\s*$')
RE_CJK_NAME = re.compile(r'^[\u4e00-\u9fff·•]{2,6}$')
RE_PERSON = re.compile(r'([\u4e00-\u9fff]{2,6})\s*(先生|女士)')
RE_ENTITY = re.compile(
    r'([A-Za-z][A-Za-z0-9\.\,\s&\-\(\)]{2,80}?(?:LIMITED|LTD\.?|INC\.?|COMPANY|CORPORATION|CORP\.?|HOLDINGS|GROUP|CAPITAL|INVESTMENT(?:S)?|SECURITIES|ASSET(?:S)?(?: MANAGEMENT)?)\b)',
    re.I)
RE_CN_ENTITY = re.compile(r'([\u4e00-\u9fffA-Za-z0-9（）()·]{2,40}?(?:有限公司|控股有限公司|集團有限公司|國際有限公司))')
RE_BENEFICIAL = re.compile(r'(?:最終)?(?:實益)?擁有人(?:為|是)\s*([^\n，。；,;]{2,40})')
RE_OWNED_BY = re.compile(r'由\s*([\u4e00-\u9fff·]{2,6})\s*(先生|女士)[^。；\n]{0,20}?(?:全資|實益|直接或間接)?(?:擁有|控制|持有)')
RE_INDEP = re.compile(r'[^。\n]*(?:獨立第三方|獨立於本公司|獨立人士)[^。\n]*')
RE_SHARES_NUM = re.compile(r'([\d,]{4,})\s*股')
RE_PCT = re.compile(r'([\d.]+)\s*%')
RE_LOCKUP = re.compile(r'(禁售|不得出售|不可出售|lock-?up)', re.I)
RE_PRICE_HKD = re.compile(r'每股[^\n。]{0,30}?([\d]+(?:\.[\d]+)?)\s*(?:港元|港幣|HK\$)')
RE_CN_DATE = re.compile(
    r'([二〇○○O零一二三四五六七八九\d]{4})年\s*([一二三四五六七八九十〇○O零\d]{1,3})月\s*([一二三四五六七八九十〇○O零\d]{1,3})日')

CN_DIG = {'零': 0, '〇': 0, '○': 0, 'O': 0, '一': 1, '二': 2, '三': 3, '四': 4,
          '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def _cn_int(s: str) -> int | None:
    s = s.strip()
    if s.isdigit():
        return int(s)
    # 十 = 10；二十二=22；一百=100（公告年份形式固定：二零二六）
    if s in ('十',):
        return 10
    m = re.fullmatch(r'([一二三四五六七八九])?十([一二三四五六七八九])?', s)
    if m:
        tens = CN_DIG[m.group(1)] if m.group(1) else 1
        ones = CN_DIG[m.group(2)] if m.group(2) else 0
        return tens * 10 + ones
    if all(c in CN_DIG for c in s) and s:
        return int(''.join(str(CN_DIG[c]) for c in s))
    return None


def cn_date_to_iso(s: str) -> str | None:
    m = RE_CN_DATE.search(s)
    if not m:
        return None
    y, mo, d = _cn_int(m.group(1)), _cn_int(m.group(2)), _cn_int(m.group(3))
    if not (y and mo and d):
        return None
    try:
        import datetime
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None

# ---------------------------------------------------------------- 釋義段落


def _clean_lines(text: str) -> list[str]:
    lines = []
    for ln in text.splitlines():
        if RE_PAGE_NO.match(ln):
            continue
        lines.append(ln.rstrip())
    return lines


def find_definition_section(lines: list[str]) -> tuple[int, int]:
    """回傳釋義段起止行號。起點=釋義/詞彙標題行；終點=文件尾或「承董事會命」。"""
    start = -1
    for i, ln in enumerate(lines):
        s = ln.strip().replace(' ', '').rstrip('：:')
        if s in ('釋義', '詞彙', '釋義及詞彙', '定義及釋義', '定義') or \
           s.startswith('釋義') and len(s) <= 6 or \
           re.match(r'^於本公告內，除非文義另有所指', s) or \
           re.match(r'^本公告內，除非文義另有所指', s) or \
           re.match(r'^除文義另有所指外', s):
            start = i
            break
    if start < 0:
        return -1, -1
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip().replace(' ', '')
        if s.startswith('承董事會命') or s.startswith('請同時參閱') or \
           re.match(r'^香港交易及結算', s):
            end = j
            break
    return start, end


def parse_definitions(lines: list[str], start: int, end: int) -> list[dict]:
    """逐行解析 「label」 指 body。多行body併入直至下一個label。"""
    defs = []
    cur = None
    for i in range(start + 1, min(end, len(lines))):
        ln = lines[i]
        if not ln.strip():
            continue
        m = RE_DEF_LINE.search(ln)
        if m:
            if cur:
                defs.append(cur)
            cur = {'label': m.group('label').strip(), 'body': m.group('body').strip()}
        elif cur is not None and not RE_NEWDEF.search(ln):
            seg = ln.strip()
            if seg and len(cur['body']) < 400:
                cur['body'] += seg
    if cur:
        defs.append(cur)
    return defs

# ---------------------------------------------------------------- 承配人候選


LABEL_PAT = re.compile(
    r'^(?:該等|所有)?\s*'
    r'(?:第[一二三四五六七八九十百]+)?'
    r'(?:配售承配人|認購人|承配人|投資者|認購方|乙方)'
    r'[A-Z甲乙丙丁戊己庚辛]?$')


def _strip_conn(s: str) -> str:
    return re.sub(r'^[由為是即該]+', '', s).strip()


def _classify(body: str) -> tuple[str, str, str]:
    """回傳 (placee_type, name, beneficial_owner)。只認原文。

    優先次序：邊種匹配喺body較前位置就用邊種（00476教訓：
    「金章科技有限公司，...由王敏女士全資擁有」——公司先出現）。
    """
    bene = None
    mb = RE_BENEFICIAL.search(body)
    if mb:
        bene = mb.group(1).strip().rstrip('）)')
    mo = RE_OWNED_BY.search(body)
    if mo and not bene:
        bene = mo.group(1) + mo.group(2)

    mp = RE_PERSON.search(body)
    me = RE_ENTITY.search(body) or RE_CN_ENTITY.search(body)
    pos_p = mp.start() if mp else 10**9
    pos_e = me.start() if me else 10**9

    if pos_e <= pos_p and me:
        nm = re.sub(r'\s+', ' ', me.group(1)).strip().rstrip('，,')
        return '公司', nm, bene
    if mp:
        return '個人', _strip_conn(mp.group(1)) + mp.group(2), bene
    # 後備：body 開頭係 2-6 個中文字（00254式：指 鄭凱斌）
    head = _strip_conn(body.strip().rstrip('，。,'))
    if RE_CJK_NAME.match(head) and bene:
        return '個人', head, bene
    if RE_CJK_NAME.match(head):
        return '個人', head, bene
    return 'UNKNOWN', None, bene


RE_LABEL_TOKEN = re.compile(
    r'(?:第[一二三四五六七八九十百]+)?(?:配售承配人|認購人|承配人|投資者|認購方)[A-Z甲乙丙丁戊己庚辛]?')


def _is_group_ref(body: str) -> bool:
    """body 係咪引用其他label嘅群組定義（如「認購人A、認購人B及認購人C」）。
    只有 >=2 個唔同label token先算（單一「投資者」泛稱唔算）。"""
    tokens = RE_LABEL_TOKEN.findall(body.replace('該等', ''))
    return len(set(tokens)) >= 2


def placee_defs(defs: list[dict]) -> tuple[list[dict], list[dict]]:
    """過濾出承配人定義項。回傳 (有名承配人, 匿名/泛稱承配人)。"""
    BLOCKLIST = ("香港聯合交易所", "聯交所", "香港交易及結算所",
                 "香港中央結算", "HKSCC", "HKEX")
    named, anon = [], []
    for d in defs:
        lab = d['label'].replace(' ', '')
        if not LABEL_PAT.match(lab):
            continue
        body = d['body'].strip()
        if not body or body in ('具有上市規則所賦予之涵義',):
            continue
        if _is_group_ref(body):
            continue
        ptype, name, bene = _classify(body)
        if name and any(b in name for b in BLOCKLIST):
            name = None  # 交易所/結算公司唔會係承配人
            ptype = 'UNKNOWN'
        mi = RE_INDEP.search(body)
        item = {
            'placee_label': d['label'].strip(),
            'placee_name': name,
            'placee_type': ptype if name else 'UNKNOWN',
            'beneficial_owner': bene,
            'independent_declared': (mi.group(0).strip()[:200] if mi else None),
            'def_body': body[:400],
        }
        if name:
            named.append(item)
        else:
            anon.append(item)
    return named, anon

# ---------------------------------------------------------------- 正文數值


def extract_event_numbers(text: str) -> dict:
    """正文層：總認購價、總股數、禁售、擴大後%、完成日期。取保守（首個匹配）。

    部分PDF全文字隔空格（二 零 二 六 年），日期/價錢regex一律行去空格文本。"""
    out = {'price': None, 'total_shares': None, 'lockup': '未載',
           'pct_enlarged_aggregate': None, 'completion_date_iso': None,
           'enlarged_issued_total': None}
    compact = re.sub(r'\s+', '', text)
    mp = RE_PRICE_HKD.search(compact)
    if mp:
        try:
            out['price'] = float(mp.group(1))
        except ValueError:
            pass
    if RE_LOCKUP.search(compact):
        out['lockup'] = '有'
    # 擴大後已發行股本絕對數（Claude覆核二·#3：EXACT_COMPUTED分母）
    m = re.search(r'擴大後[^。\n]{0,50}?已發行股本(?:總數)?(?:約|為|共)?([\d,]{6,})股', compact)
    if m:
        try:
            out['enlarged_issued_total'] = int(m.group(1).replace(',', ''))
        except ValueError:
            pass
    # 完成日期（句式：已於X完成／完成已於X發生／已於X獲配發及發行）
    for m in re.finditer(
            r'(?:已於|於)([二〇○○O零一二三四五六七八九\d]{4}年[一二三四五六七八九十〇○O零\d]{1,3}月[一二三四五六七八九十〇○O零\d]{1,3}日)'
            r'(?:(?:已完成|完成|發生|獲配發及發行|配發及發行))|(?:完成已於)'
            r'([二〇○○O零一二三四五六七八九\d]{4}年[一二三四五六七八九十〇○O零\d]{1,3}月[一二三四五六七八九十〇○O零\d]{1,3}日)發生', compact):
        iso = cn_date_to_iso(m.group(1) or m.group(2))
        if iso:
            out['completion_date_iso'] = iso
            break
    return out


def shares_for_label(text: str, label: str, label_base: str | None = None) -> int | None:
    """喺正文搵label對應股數。支援：
    1) 「{label}...認購N股」直接句式
    2) 「各{base}／每名{base}...認購N股」泛稱句式（02113式）
    3) 表格式：{label} 後短距離出現 N股
    """
    esc = re.escape(label.replace(' ', ''))
    pat = re.compile(
        esc + r'[^。;\n]{0,80}?(?:認購|配發|發行|買)[^\d\n]{0,40}([\d,]{4,})\s*股')
    m = pat.search(text)
    if m:
        try:
            return int(m.group(1).replace(',', ''))
        except ValueError:
            return None
    base = label_base or RE_LABEL_TOKEN.sub('', '')  # 呢個唔會命中，走下面
    mb = re.match(r'^(.*?)[A-Z甲乙丙丁戊己庚辛]?$', label.replace(' ', ''))
    base = mb.group(1) if mb and mb.group(1) else None
    if base:
        gesc = re.escape(base)
        gpat = re.compile(
            r'(?:各|每名)' + gesc + r'[^。;\n]{0,60}?(?:認購|配發|發行|買)'
            r'[^\d\n]{0,40}([\d,]{4,})\s*股')
        m = gpat.search(text)
        if m:
            try:
                return int(m.group(1).replace(',', ''))
            except ValueError:
                return None
    return None

# ---------------------------------------------------------------- 主入口

def _parse_text(text: str, engine: str) -> dict:
    res = {
        'engine': engine, 'scanned': is_scanned(text), 'text': text,
        'rows': [], 'anon_rows': [], 'event_numbers': extract_event_numbers(text),
        'def_found': False, 'quality': -100,
    }
    if res['scanned'] or not text:
        return res
    lines = _clean_lines(text)
    start, end = find_definition_section(lines)
    if start < 0:
        return res  # 完成公告冇釋義段，但event_numbers已抽
    res['def_found'] = True
    defs = parse_definitions(lines, start, end)
    named, anon = placee_defs(defs)
    res['rows'] = named
    res['anon_rows'] = anon
    res['defs_all'] = defs
    # 質素分：有承配人 > 有定義 > 亂碼罰分；標籤多過「指」配對 = 雙欄錯位（08245式）
    n_label_lines = sum(1 for ln in lines[start:end] if ln.strip().startswith('「'))
    n_defs = len(defs)
    res['quality'] = (10 * len(named) + 2 * n_defs
                      - 3 * len(RE_MOJIBAKE.findall(text[:5000]))
                      - 5 * max(0, n_label_lines - n_defs))
    return res


def parse_announcement(pdf_path: pathlib.Path) -> dict:
    """單一公告 → 結構化。rows=[] 表示釋義中冇具名承配人定義。

    雙引擎：pdftotext -layout 優先（快）；若定義段有錯位跡象
    （08245式雙欄表格）或質素差，改用pdfplumber再比較。
    """
    text, engine = extract_text(pdf_path)
    res = _parse_text(text, engine)
    need_better = (not res['def_found']) or (res['quality'] <= 0) or res['scanned']
    if need_better and engine != 'pdfplumber':
        t2 = _pdfplumber_text(pdf_path)
        res2 = _parse_text(t2, 'pdfplumber')
        if res2['quality'] > res['quality']:
            return res2
    return res


def snippet_from(text: str, name: str, limit: int = 200) -> str:
    """搵姓名首次出現處，切出<=200字上下文片段。"""
    if not name:
        return ''
    idx = text.find(name)
    if idx < 0:
        return ''
    s = max(0, idx - 80)
    seg = text[s:idx + len(name) + 100]
    seg = re.sub(r'\s+', ' ', seg).strip()
    return seg[:limit]
