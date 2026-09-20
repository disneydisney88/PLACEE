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

---

## [P4.5] DI深挖：高警示個案R3/R5/R6實測（2026-09-20）

### 1. DI站狀態
- `di.hkex.com.hk` 09-19回「暫時未能提供」→ 09-20實測**恢復正常**（非封鎖，屬站方暫時問題）。
- 可用路線＝瀏覽器：www2.hkexnews.hk DI入口 → DION `NSSrchMethod.aspx` → 「Search by listed corporation」→ List of all notices（GET URL帶sid/sd/ed參數可直接導航）。表單postback同日期下拉用evaluate設定再`cmdSearch.click()`。
- 紀律：每次抓取間隔≥3秒；全程約10次fetch，無封鎖、無驗證碼。**requests直連仍會403（WAF照在），自動化必須行瀏覽器**。

### 2. 實測結果（alerts.csv已更新＋新欄R3/R5/R6_evidence，registry.db已重建）

| 個案 | R3 | R5 | R6 | 核心證據 |
|---|---|---|---|---|
| 00254 國家聯合資源 | FALSE | **TRUE** | **TRUE** | Form3A `DA20260602E00374`：董事**賀遠帆** 05-29（公告05-28翌交易日）場內沽34,800,000股均價HKD0.95（高0.96）＞認購價0.77，持倉6.21%→0.00%；前置＝`DA20260602E00373` 04-24場外@0.66買入35M股（12.42%）。 |
| 02113 世紀集團國際 | **TRUE** | FALSE | FALSE | Form1 `IS20260902E00490`：**鄧林輝** 09-01（公告前一日）場外現金@0.134認購225,330,000股，0%→**28.00%**——正落25-29.99%帶、低過30%全面要約線；申報日09-02與公告同日。 |

- 00254賀遠帆形態＝「公告前場外埋伏（0.66）→公告翌日場內高價清倉（0.95）」，R5/R6兩燈齊中，同時解釋06-25崩盤前嘅內部人離場。
- 00254窗口（02-27..08-26）共13宗申報：付尚輝06-12場外@0.77完成認購58M股（8.58%，即placees.csv第三承配人）；Ji Kaiping/Thousand Joy 14.39%、Guo Peiyuan/Hontin Ocean 9.11%、LI ZIWEI 5.92%——**無任何塊落25-29.99%**→R3=FALSE。
- 02113窗口（06-04..09-20）僅2宗申報：鄧林輝認購＋09-14「20合1」股本調整（`IS20260915E00640`，225,330,000→11,266,500股，28.00%不變）。0宗沽售、0宗董事申報→R5/R6=FALSE。**窗口後段（至12-01）未屆滿，FALSE僅代表「至今無」**，evidence欄已註明。

### 3. 口徑註
- 00254認購價＝0.77（placees.csv/公告PDF）；任務書寫0.85——沽售均價0.95兩個口徑都高過，verdict不變。
- 02113 DI申報均價0.134＝任務書「6.70調整前」嘅調整後對應口徑（6.70÷50=0.134）。
- alert_score唔變（R3/R5/R6唔入評分，見KNOWN_ISSUES 0b）。

### 4. 下游
- `alerts.csv`：27→30欄（加R3_evidence/R5_evidence/R6_evidence），其餘724行新欄留空、原欄不變。
- `python src/build_registry.py` 重建✓（alerts 725行）；`scripts/sync_drive.ps1` 同步✓。

## 最终同步验证（2026-09-20 20:40）

- G:\我的雲端硬碟\PLACEE\data\ 与本地 data/ 完全一致（9檔+input/子目錄，檔案大小時間戳吻合）
- registry.db 行數：placees 777 / outcomes 725 / alerts 725 / post_go_placees 226 / wh_flags 6 / repeat_placees 3
- R2三級制最終驗證：55行/35宗可餵，02113 R2a+R2b+R2c 全中

---

## [P4.6] DI補測：12宗crash個案 R3/R5/R6（2026-09-20）

### 1. 事件：P4.5證據被pipeline重生成沖走（已永久修復）
- P4.6進行中發現另一session嘅pipeline重跑（commit 5026698/d5b5f2e）**重新生成alerts.csv，沖走P4.5手改嘅R3/R5/R6_evidence欄**。
- 修復：實測結果改放**data/di_evidence.csv sidecar**（鍵=stock_code+ann_date），`src/alerts.py`寫出前自動左連接合併——**以後任何pipeline重生成都不會沖走**（重跑驗證：13行證據完整保留）。
- 教訓：手改生成物會被沖；實測數據必須行sidecar+merge。

### 2. 實測結果（11宗crash事件，全部實測）

| 個案 | R3 | R5 | R6 | 要點 |
|---|---|---|---|---|
| 00145 信能低碳 | FALSE | FALSE | FALSE | 3宗全借貸池類（Cheng Lut Tim 1.56%封頂） |
| **00648 京玖康療** | FALSE | **TRUE** | FALSE | Form1 `IS20260625E00454` 黃杰05-15沽22.25M股@2.20（>>認購價0.28），51.00%→30.30%（貼30%線上停）。惟同一人07-05以同價2.20買入——平手搬倉，非低位獲利離場，evidence已註明 |
| 01421 恒昌集團(2024) | FALSE | FALSE | FALSE | 2宗1316借貸池（YAO RUNXIONG 3.64%） |
| 01796 中國數智科技 | FALSE | FALSE | FALSE | 控股股東謝兆凱crash日(04-09)場內沽51.1M股均價0.389（<<3.0），個人層38.61%→27.96%；沽價全低於認購價→R5唔中；場內非場外→R3唔中 |
| 01894 恒益控股 | FALSE | FALSE | FALSE | 窗口僅1宗且已撤回（withdrawn） |
| 01961 多牛科技 | FALSE | FALSE | FALSE | 窗口零申報 |
| 02110 天成控股 | FALSE | FALSE | FALSE | 7宗無沽售（LIN LIN 1101經Form證實係買入） |
| 02330 中國上城 | FALSE | FALSE | FALSE | 4宗全係承配人28-10買入@0.18（8.33%/8.25%/15.90%） |
| 02617 藥捷安康－Ｂ(×2) | FALSE | FALSE | FALSE | 38宗零沽售；董事Wu Frank 25.78-26.53%帶內坐貨係攤薄形成（1711無交易）；VC反而在06-08月@11-13.7撈底 |
| 02685 量化派 | FALSE | FALSE | FALSE | 9宗全係Fosun系crash後買入（07-28 @7.29、08-26 @3.98） |

- **全registry R3/R5/R6唯一TRUE：00254(賀遠帆R5+R6)、02113(鄧林輝R3)、00648(黃杰R5)。**
- 註：清單頁reason代碼（1201/1101）會誤導——**必須開Form詳情睇原文**（00648/01796兩案清單話買、Form原文係賣；02110相反）。

### 3. 下游
- `data/di_evidence.csv`（13行）＋`src/alerts.py`合併步驟＋`deploy_evidence/di_p46_crash_notices.json`（原始申報清單）。
- alerts.csv重生成（725行，30欄，13行有DI證據）；registry.db重建✓；Drive同步✓。
- crash_cases.csv已由另一session擴至18宗（00362/00653/01010/01872/08087/08426六宗2024-25舊案）——**未做DI**，留待下一輪。
