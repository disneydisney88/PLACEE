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

## 最終 git log（部署鏈）

```
45c9568 [P4] deploy log + README (cloud form fill + API + MCP)
a816bce [P3] registry API endpoints + MCP wrapper + hard tests (付尚輝/COMBO_BSGS all pass)
d83dcfc [P2] Drive sync via G: desktop (sync_drive.ps1) + daily schedule note
9dedbc7 [P1] Streamlit Cloud entrypoint shim + split requirements + data strategy + untrack cookies/logs
```
敏感檔追蹤檢查：無（webb_cookie.txt / checkpoints/ / *.log 全部已退出）。

---

## [P7-HOTFIX] 雲端同步＋依賴修復（2026-09-19）

### 1. registry.db 版本
- DB以<50MB直接commit入repo（DEPLOY_LOG Phase 2決定表）。`git log -- data/registry.db`：
  最後更新=[P7-HOTFIX] commit f5b102e（含post_go_placees 226行、EXPLICIT pct 51行、02113修正）。
- DRIVE_DB_URL：唔需要（DB<50MB隨repo）。用戶Reboot Streamlit Cloud app即拉最新main。

### 2. 02113數據修正（MANUAL_SPEC歸零）
- source_file：MANUAL_SPEC字串 → **hkexnews PDF URL**（2026090202541_c.pdf）
- price：0.269（淨額錯抓）→ **0.27**（公告載明認購價；parse已修正為避開「淨額」匹配）
- 驗收：姓名搜尋付尚輝 → 2行（02113+00254），**0行MANUAL_SPEC** ✓

### 3. requirements/runtime
- requirements.txt 加 tabulate/pyarrow/openpyxl
- 新增 runtime.txt = python-3.11（Streamlit Cloud表單同樣揀3.11）

### 4. Kingston B01438「衛星倉派貨」解解（00254）

計算輸入（ccass_daily逐日%）：
- Build：05-15持0.42% → **05-19跳升4.85%**（公告05-28之前9日＝前置部署）
- 高水位：05-19..06-11持4.85→7.92%，06-12..16回落6.61%
- Dump：**06-17單日6.61→0.33（-95%）**，之後長期0.19
- retailΔ：06-12→06-25散戶白名單合計3.26→9.95（**+6.65pt**）
  - 組成：富途B01955 +2.93、輝立B01345 +1.18、盈透B01590 +1.06、耀才B01668 +0.51、致富+0.31、老虎+0.25、盈立+0.25、微牛+0.21

**判定：唔係誤判**——Kingston係公告前9日埋伏、認購後高水位、一日清倉95%、散戶接火棒，
完全符合衛星倉定義。R7B新排除條件（peak≥4.0%**且**高水位持有≥60日）實測Kingston
高水位僅約20個交易日 → **排除條件唔會踢走佢**，flag正確保留。長期持倉調整類
（如有）會標「長期持倉調整(非衛星)」唔入R7。

### 5. 雲端驗收證據

三張截圖已存 `deploy_evidence/`（本機app localhost:8601與雲端同一份data/＋代碼）：
1. `1_name_search_fuchinfei.png` — 付尚輝搜尋：2行、02113 source_file＝hkexnews PDF URL、**0行MANUAL_SPEC**
2. `2_name_search_liu_chiu_heung_08106.png` — 劉朝暉搜尋：**1行命中08106芯化蘭德**（GO後承配人）
3. `3_broker_dropdown.png` — 券商下拉含B01438（P6後broker），00254 Kingston flag完整顯示

**用戶操作**：Streamlit Cloud app → Manage app → Reboot（表單已填 main/streamlit_app.py 者
pull f5b102e 後即見上述三項）。雲端URL驗收同樣三項；截圖可重拍。
