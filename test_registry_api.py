# -*- coding: utf-8 -*-
"""test_registry_api.py — 硬測試（任務書§3.2）：3項必過

跑法：先起 uvicorn api_registry:app --port 8765，再 python test_registry_api.py
（本腳本會自己spawn server subprocess）
"""
import subprocess
import sys
import time

import requests

BASE = "http://localhost:8765"
proc = None


def wait_up(timeout=30):
    global proc
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_registry:app",
         "--port", "8765", "--log-level", "warning"],
        cwd=".")
    for _ in range(timeout * 2):
        try:
            if requests.get(f"{BASE}/registry/meta", timeout=3).ok:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("server未能啟動")


def main():
    wait_up()
    ok = True

    # 硬測試1：/registry/repeat 含付尚輝（00254+02113）
    r = requests.get(f"{BASE}/registry/repeat?min_count=2").json()
    fs = [x for x in r["rows"] if "付尚輝" in x["placee_name"]]
    t1 = bool(fs) and "00254" in fs[0]["stock_codes"] and "02113" in fs[0]["stock_codes"]
    print(f"T1 repeat含付尚輝(00254+02113): {'PASS' if t1 else 'FAIL'}")
    ok &= t1

    # 硬測試2/3：/registry/stock/{code} 含 COMBO_BSGS
    for code in ("02113", "00254"):
        r = requests.get(f"{BASE}/registry/stock/{code}").json()
        flags = [f["flag_level"] for f in r["wh_flags"]]
        combo = "COMBO_BSGS" in flags
        print(f"T{'2' if code=='02113' else '3'} stock/{code} 含COMBO_BSGS: "
              f"{'PASS' if combo else 'FAIL'} (flags={flags})")
        ok &= combo

    # 附加：name查詢、crash、meta可用性
    r = requests.get(f"{BASE}/registry/name", params={"q": "付尚輝"}).json()
    print(f"extra name查詢行數: {len(r)}")
    r = requests.get(f"{BASE}/registry/crash?days=30").json()
    codes = {x["stock_code"] for x in r["rows"]}
    print(f"extra crash個案: {len(r['rows'])}宗, 含00254: {'00254' in codes}")

    print("ALL PASS" if ok else "SOME FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        if proc:
            proc.terminate()
