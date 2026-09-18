# streamlit_app.py — Streamlit Cloud entrypoint shim
# repo root 為工作目錄；先載 src 入 path、落 bootstrap（雲端時自動抓 DB）、
# 再以 __main__ 身份執行 src/app.py（不改動 src/app.py 本身）。
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

try:
    import bootstrap  # noqa: F401  # 確保 data/registry.db 存在（雲端下載fallback）
except Exception as e:  # 本機無網絡等情況唔好阻住啟動
    print(f"bootstrap skip: {e}")

import runpy  # noqa: E402

runpy.run_path(os.path.join(ROOT, "src", "app.py"), run_name="__main__")
