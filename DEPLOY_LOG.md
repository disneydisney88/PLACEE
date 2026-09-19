# DEPLOY_LOG.md — PLACEE 上雲三件套部署日誌

執行：zcode｜日期：2026-09-19｜任務書：claude_ZCODE任務_PLACEE上雲三件套_20260918.md

---

## Phase 0 盤點（完成）

| 項目 | 實際 |
|---|---|
| Branch | `main`（ls-remote確認：repo本來係空嘅，首次push建立main） |
| 本機pipeline位置 | `C:\Users\klcho\.zcode\workspace\default\hk-placee-registry\` |
| app入口 | `src/app.py`（Streamlit，4頁） |
| registry.db | 585KB（**<50MB → 直接commit入repo**，Drive為備份） |
| requirements | 已拆分：app-only（requirements.txt）vs pipeline（requirements-pipeline.txt） |
| Python | 3.13本機；Cloud表單建議3.11 |

## 用戶部署表單填法（Streamlit Cloud → New app）

| 欄位 | 填 |
|---|---|
| Repository | `disneydisney88/PLACEE` |
| Branch | **`main`**（唔係master） |
| Main file path | **`streamlit_app.py`**（root shim，會自動載src/app.py） |
| Python version | 3.11 |
| Advanced → Secrets | **唔使填**（registry.db已隨repo commit；只有DB>50MB先需要`DRIVE_DB_URL`） |

## Phase 1 修復 Streamlit Cloud 部署（完成）

- [x] Branch問題：直接推`main`，無建master
- [x] Root shim `streamlit_app.py`：sys.path+chdir+runpy載src/app.py；本地驗證HTTP 200（port 8602），行為與`streamlit run src/app.py`一致
- [x] `src/bootstrap.py`：DB缺失時從`DRIVE_DB_URL`（env或Secrets）下載fallback
- [x] requirements拆分完成
- [x] `.gitignore`強化：**checkpoints/（含webb_cookie.txt！）已全部退出git追蹤**、*.log、.env、secrets/
- [x] Commit `[P1]`，push origin main成功
- app URL：待用戶按上面表單部署後生效

## Phase 2 Google Drive 數據同步（完成 — 簡化版）

**決定（比任務書更簡單）**：用戶機已裝 Google Drive 桌面同步（G: 碟），
`G:\我的雲端硬碟\PLACEE\` 就是Drive——**唔使rclone、唔使OAuth**，直接檔案複製。

- [x] 已放入：`G:\我的雲端硬碟\PLACEE\data\`（registry.db＋6個CSV）
- [x] 已寫 `G:\我的雲端硬碟\PLACEE\README.md`（詳細數據字典+更新方法）
- [x] 同步腳本：`scripts/sync_drive.ps1`（robocopy鏡像 data/ → Drive folder，排除cache/checkpoints）
- [x] 排程：zcode每日23:00自動同步（CronCreate）；pipeline尾端接入
- [x] `DRIVE_DB_URL`：**暫不需要**（DB<50MB已入repo）。若日後DB>50MB：喺Drive網頁對
      `PLACEE/data/registry.db` right-click→分享→複製連結，轉成
      `https://drive.google.com/uc?export=download&id=<ID>` 填入Secrets即可（bootstrap.py已支援）

## Phase 3 MCP / API 層（完成 — 本機可跑；Render部署留一句指令）

- [x] `api_registry.py`：FastAPI，7個endpoint（見任務書§3.2），DB來源=repo內data/registry.db
- [x] 硬測試：`test_registry_api.py` — 3項全過（付尚輝00254+02113／02113 COMBO_BSGS／00254 COMBO_BSGS）
- [x] `mcp_server.py`：mcp Python SDK stdio，7個tool（registry_name/broker/stock/alerts/repeat/crash/meta）
- [ ] Render部署：一句指令留俾用戶（見下「用戶一句指令」）

### 用戶一句指令（Render部署，可選）

```
Render Dashboard → New + → Web Service → Existing Repo → disneydisney88/PLACEE
→ Name: placee-api → Runtime: Python 3 → Build: pip install -r requirements-api.txt
→ Start: uvicorn api_registry:app --host 0.0.0.0 --port $PORT
```

## Phase 4 文件與收尾（完成）

- [x] DEPLOY_LOG.md（本檔）
- [x] README.md更新（Cloud部署表單填法＋API＋MCP接入）
- [x] git log檢查：無cookies/logs/checkpoints外洩（webb_cookie.txt已退出追蹤）

## BLOCKED 項

無。全部按預設決定表行。

## git log（部署相關）

見 `git log --oneline`：`[P1]`、`[P2]`、`[P3]`、`[P4]` 四個commit。
