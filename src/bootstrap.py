# -*- coding: utf-8 -*-
"""bootstrap.py — 雲端啟動時確保 data/registry.db 存在

本機：DB 已存在，即返。
雲端（Streamlit Cloud等）：DB 隨 repo commit（<50MB）——存在即返；
若被 .gitignore 排除嘅部署，改用環境變數/Secrets DRIVE_DB_URL 下載。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "registry.db")


def _download(url: str, dest: str) -> None:
    import requests
    import streamlit as st
    with st.spinner("下載 registry.db ..."):
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)


def main() -> None:
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 1000:
        return
    url = os.environ.get("DRIVE_DB_URL", "")
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get("DRIVE_DB_URL", "")
        except Exception:
            url = ""
    if url:
        _download(url, DB_PATH)


main()
