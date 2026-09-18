# -*- coding: utf-8 -*-
"""hkex_client.py — HKEXnews 禮貌抓取客戶端（H1實測可用端點，見 00_probe.md）

規格紀律：
- 每次請求間隔 >= 1.6 秒（單線程）
- 失敗重試最多 3 次，指數退避（2s/4s/8s）
- User-Agent 標明用途
- PDF 落 cache/pdf/，重跑唔會重抓
"""
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www1.hkexnews.hk"
UA = "hk-placee-registry/1.0 (academic research on HKEX public disclosures; polite crawler; contact: local user)"
MIN_INTERVAL = 1.6
MAX_TRIES = 3

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PDF = ROOT / "cache" / "pdf"
CACHE_PDF.mkdir(parents=True, exist_ok=True)
CKPT = ROOT / "checkpoints"
CKPT.mkdir(parents=True, exist_ok=True)
STOCK_ID_FILE = CKPT / "stock_ids.json"

_last_hit = 0.0


def _sleep_rate():
    global _last_hit
    wait = MIN_INTERVAL - (time.time() - _last_hit)
    if wait > 0:
        time.sleep(wait)
    _last_hit = time.time()


def _get(path_or_url: str, params: dict | None = None, *, binary: bool = False,
         timeout: int = 60) -> bytes | str:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = path_or_url if path_or_url.startswith("http") else BASE + path_or_url
    url += qs
    delay = 2.0
    last_err = None
    for attempt in range(1, MAX_TRIES + 1):
        _sleep_rate()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return raw if binary else raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise FileNotFoundError(f"HTTP {e.code}: {url}") from e
            last_err = f"HTTP {e.code}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < MAX_TRIES:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"GET {url} 失敗 {MAX_TRIES}次: {last_err}")


def _load_json(path: pathlib.Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_json(path: pathlib.Path, obj: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(path)


def resolve_stock_id(code: str) -> str:
    """五位數代號 → HKEX 內部 stockId（帶 checkpoint 快取）。"""
    code = str(code).zfill(5)
    cache = _load_json(STOCK_ID_FILE)
    if code in cache:
        return cache[code]
    text = _get("/search/prefix.do", {
        "callback": "callback", "lang": "ZH", "type": "A",
        "name": code, "market": "SEHK"})
    m = re.search(r'\{"stockId":(\d+),"code":"%s"' % code, text)
    if not m:
        # 後備：容許 stockInfo 內任何順序
        m = re.search(r'"code":"%s","name":"[^"]*","stockId":(\d+)' % code, text) or \
            re.search(r'"stockId":(\d+),"code":"%s"' % code, text)
    if not m:
        raise ValueError(f"prefix.do 搵唔到 {code}")
    sid = m.group(1)
    cache[code] = sid
    _save_json(STOCK_ID_FILE, cache)
    return sid


def search_titles(stock_id: str, date_from: str, date_to: str) -> list[dict]:
    """titleSearchServlet.do；date_from/to = YYYYMMDD。回傳 row list。"""
    text = _get("/search/titleSearchServlet.do", {
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0",
        "market": "SEHK", "stockId": stock_id, "documentType": "-1",
        "fromDate": date_from, "toDate": date_to, "title": "",
        "searchType": "1", "t1code": "-2", "t2Gcode": "-2", "t2code": "-2",
        "rowRange": "200", "lang": "ZH"})
    d = json.loads(text)
    rows = json.loads(d.get("result", "[]"))
    out = []
    for r in rows:
        out.append({
            "date": r.get("DATE_TIME", ""),       # DD/MM/YYYY
            "time": r.get("DATE_TIME", ""),
            "title": (r.get("TITLE") or "").replace("\r", " ").replace("\n", " "),
            "file": r.get("FILE_LINK", ""),
            "pdf_url": BASE + r.get("FILE_LINK", ""),
        })
    return out


def download_pdf(pdf_url: str) -> pathlib.Path:
    """下載 PDF 至 cache/pdf/（以檔名去重；已存在即秒回）。"""
    fname = pdf_url.rsplit("/", 1)[-1]
    if not fname:
        raise ValueError("bad pdf url " + pdf_url)
    dest = CACHE_PDF / fname
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    raw = _get(pdf_url, binary=True)
    if not raw.startswith(b"%PDF"):
        raise ValueError(f"唔係PDF: {pdf_url[:100]}")
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(dest)
    return dest
