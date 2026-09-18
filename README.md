# hk-placee-registry — 承配人索引庫與亮燈引擎

由「姓名」或「券商組合」反查全部歷史配股／認購個案，並自動標示高危組合。

> 目的：`配股事件20260831.csv` 有500宗配股／認購事件，但只有配售代理，冇承配人姓名。
> 承配人姓名只存在於HKEX公告PDF嘅「釋義」段落。本工具建成索引後，
> 同一姓名第二次出現即可即時識別。學術研究及風險分析用途，不構成投資建議。

## 快速開始

```bash
# 環境：Python 3.13+，需要 pdftotext（poppler）喺 PATH
pip install pandas streamlit pdfplumber requests lxml

# 1) 抽承配人（主批量：配股500+供股200，斷點續傳，HKEX禮貌抓取1.6s/請求）
python src/fetch_hkex.py --all          # 首跑約2.5-4小時；中斷後重跑同一指令即續

# 2) 補近期日線（8月後事件結局用，經webbsite-ccass-api/Yahoo）
python src/backfill_prices.py

# 3) CCASS 衛星倉（Tier1=00254/02113全窗；Tier2=有具名承配人事件 D-10..D+25）
python src/fetch_ccass.py tier1
python src/fetch_ccass.py tier2

# 4) 偵測器 → data/warehouse_flags.csv
python src/detect_warehouse.py

# 5) 結局標註 → data/outcomes.csv（T+30/60/90、回撤、crash、爆量）
python src/outcomes.py

# 6) 亮燈引擎 → data/alerts.csv + data/repeat_placees.csv
python src/alerts.py

# 7) 建庫 → data/registry.db
python src/build_registry.py

# 8) 查詢介面
streamlit run src/app.py
```

## 產出檔案（data/）

| 檔案 | 內容 | 驗收 |
|---|---|---|
| `placees.csv` | 每名承配人一行：姓名/類別/實益擁有人/股數/認購價/擴大後%/禁售/完成日/`source_url`/`snippet`(≤200字)/`parse_confidence` | 覆蓋率與準確率見 `parser_report.md` |
| `repeat_placees.csv` ★ | 同一姓名跨≥2隻股票嘅候選清單（**唔自動合併判斷**，規格§九.4） | 必過測試：付尚輝（00254+02113） |
| `warehouse_flags.csv` | 衛星倉建倉→派貨 + `COMBO_BSGS`（寶新B01666+粵商國際B02014同時出現） | 必過測試：00254@2026-06、02113@2026-08/09 |
| `outcomes.csv` | T+30/60/90回報、完成日起回報、90日最大回撤、單日>50%崩盤、成交爆量倍數 | 合股已校正（02113 20:1於2026-09-14生效） |
| `alerts.csv` | R1-R9規則布林欄＋`alert_score`；≥3=高度警示 | 見下表 |
| `registry.db` | SQLite：placees/outcomes/wh_flags/alerts/repeat_placees + `v_name_search`視圖 | — |

## 亮燈規則

| # | 規則 | 資料源 | 狀態 |
|---|---|---|---|
| R1 | 寶新(B01666)+粵商國際(B02014)同時出現 | warehouse_flags | ✅ 實測命中00254/02113 |
| R2 | ≥3名自然人承配人、分配均等(std<0.1)且全部<5% | placees | ✅ |
| R3 | 控股塊場外易手25-29.99% | 需DI | `NOT_TESTED` |
| R4 | 配售價貼20%折讓下限（price/基準×0.8∈[0.98,1.02]） | placees+outcomes | ✅ |
| R5 | 既有股東/董事高價離場 | 需DI | `NOT_TESTED` |
| R6 | 利好翌日董事場內減持 | 需DI | `NOT_TESTED` |
| R7 | 衛星倉派貨（建倉<1%→>3%≤10日，其後≤20日淨減>50%，散戶合計+2pt） | CCASS | ✅ 實測命中02113 |
| R8 | 事件前90日成交中位數<50萬（低成交殼） | 價格庫 | ✅ |
| R9 | 競價異常U盤>20% | 需逐筆 | `NOT_TESTED` |

`alert_score` = R1..R9命中數（NOT_TESTED不計入）。

## 資料字典（placees.csv 主要欄位）

| 欄位 | 說明 |
|---|---|
| `placee_name` | **原文姓名，不作任何加工**；抽唔到=空＋`fail_reason` |
| `placee_type` | 個人／公司／UNKNOWN |
| `beneficial_owner` | 公告有列先填（例：認購人A=由王敏女士全資擁有之公司） |
| `shares` / `price` / `pct_enlarged` | 公告原文數字；`pct_enlarged`若由總數×比例推算會降級`parse_confidence=MED` |
| `below_5pct` | TRUE/FALSE/NULL（冇%數據=NULL，唔估） |
| `lockup` | 有／無／未載 |
| `source_url` | HKEX公告PDF直鏈（lang=ZH，_c.pdf） |
| `snippet` | 姓名上下文原文片段（≤200字） |
| `parse_confidence` | HIGH（pdftotext正常解析）/ MED（含推算或pdfplumber後備）/ LOW（掃描圖） |
| `fail_reason` | NO_ANN_FOUND / NO_PLACEE_DEF / NO_NAMED_PLACEE(泛稱定義冇具名) / PDF_NO_TEXT / PLACEE_NAME_SCRUBBED … |

## 紀律保證（規格§一對應）

1. **不捏造**：抽唔到→NULL＋fail_reason。`below_5pct`冇數據=NULL。
2. **不推測補全**：公告只寫泛稱（例：「承配人指配售代理促成之投資者」）→ `NO_NAMED_PLACEE`，唔會估一個名出嚟。
3. **同名不合併**：`repeat_placees.csv`只係候選清單（同一姓名唔同股票各自獨立成行）。
4. **可追溯**：每行有`source_url`＋`snippet`＋`input_row`＋`source_file`。
5. **禮貌抓取**：HKEX/webb鏡像全域1.6s間隔；失敗重試3次指數退避；UA標明用途；404唔重試。
6. **斷點續傳**：`checkpoints/fetch_state.json`（事件級）、`ccass_state.json`（股×日級）、PDF快取`cache/pdf/`。

## 已知陷阱處理（規格§九對應）

| 陷阱 | 處理 |
|---|---|
| 合股/拆股 | `outcomes.py`以`合股事件/拆股事件20260831.csv`還原（A股舊→B股新：生效日前adj_close×A/B）。02113 20:1於2026-09-14生效：base=134.0(=6.70×20)驗證通過 |
| 公司改名 | 以5位代號為主鍵 |
| 繁簡混用 | 原文儲存（HKEX中文公告以繁體為主，未額外轉換） |
| 同名不同人 | repeat_placees僅候選，人手判斷 |
| 掃描版PDF | `parse_confidence=LOW`＋`PDF_NO_TEXT`；**冇做OCR**（規格明令唔好OCR後當可靠） |
| T+2入冊 | CCASS%序列用`ffill`顯示持有期；派貨偵測以「淨變化」計，唔靠單日歸因；場外即日轉讓唔做一刀切假設 |
| HKEX限流 | 1.6s全域間隔＋指數退避；被封會以ChallengeError/重試失敗顯式報錯，唔用代理繞過 |

## webb-database.com 鏡像cookie（CCASS資料源）

鏡像有JS cookie挑戰（`/432182.js`）。解法：用ZCode內置瀏覽器開一次choldings頁，
抽出`ayuus` cookie＋完整UA存入`checkpoints/webb_cookie.txt`（第1行UA、第2行Cookie）。
挑戰失效時`fetch_ccass.py`會連續3次失敗後停機並寫`NEED_COOKIE.flag`——更新cookie後重跑同一指令即續。

## Streamlit 查詢介面

```bash
streamlit run src/app.py
```

四個頁面：①姓名搜尋（部分匹配＋原文snippet＋來源連結）②券商搜尋（衛星倉flag）③亮燈榜（score/年份/授權篩選）④個案詳情（承配人表＋CCASS持股折線＋收市價＋結局指標）。
規格要求「所有數字旁必須可點開source_url；冇來源嘅數字唔好顯示」：承配人表每行有「🔗公告」連結欄，冇來源嘅欄位顯示空值。
