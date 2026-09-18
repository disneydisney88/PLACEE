# KNOWN_ISSUES — 已知問題、降級項目與取捨記錄

更新：2026-09-18（通宵任務進行中）

## 降級項目（規格§6.3明令允許：唔可以留空或估 → 標NOT_TESTED）

| 規則 | 狀態 | 原因 |
|---|---|---|
| R3 控股塊場外易手25-29.99% | `NOT_TESTED` | `di.hkex.com.hk`為ASP.NET postback表單，本地直連被WAF擋（403）；webb-site dealings資料唔齊全。風險按規格降級 |
| R5 既有股東/董事高價離場 | `NOT_TESTED` | 同上（需DI） |
| R6 利好翌日董事場內減持 | `NOT_TESTED` | 同上（需DI） |
| R9 競價U盤異常 | `NOT_TESTED` | 需逐筆/競價數據（規格標明可選） |

**DI若要補做**：可試DisclosureTracker個股頁經瀏覽器（同webb鏡像cookie手法），或手動輸入。本晚未排入。

## 已知解析盲點

1. **泛稱承配人定義（NO_NAMED_PLACEE）**：經紀配售公告好常見「承配人指配售代理促成之任何投資者」——公告本來就冇名。呢類行係誠實輸出，唔係抓漏。比例見`parser_report.md`。
2. **雙欄釋義表錯位**：pdftotext -layout會交錯欄位（08245實例）。已用質素評分自動轉pdfplumber重抽；極端排版仍可能錯配，凡經pdfplumber後備者`parse_confidence`最高只會MED（pdfplumber純文字流冇表格框線做驗證）。
3. **「認購人A」由「由XXX女士全資擁有」定義**：公司名正確入`placee_name`、擁有人入`beneficial_owner`；但若公告冇寫公司名（只寫「由XXX女士（全資）擁有之公司」），`placee_name`=空＋UNKNOWN——未經証實嘅實體名唔會虛構。
4. **snippet以姓名首次出現處切片**：姓名若喺正文出現喺釋義之前，snippet取正文版本（仍屬同一公告原文）。
5. **交易所/結算公司誤入承配人**（香港聯合交易所等）已在parser加blocklist＋`alerts.py`洗掃（`PLACEE_NAME_SCRUBBED`）。
6. **英文版公告**：本工具只抓`lang=ZH`（_c.pdf）。極少數只有英文版公告嘅個案會`NO_ANN_FOUND`——有需要再補。

## 資料覆蓋限制

1. **價格庫截於2026-08-04**（hk_prices_master.csv）。8月後日線經webbsite-ccass-api（Yahoo源）backfill（85股，cache/price_backfill.csv）。Yahoo同tencent源口徑可能有微差；`turnover`於backfill部分為估算值（volume×close，API自己有data_quality_warnings聲明）。
2. **CCASS Tier-2視窗縮水**：規格要求D-30..D+60；實際Tier-2（非必過個案）用D-10..D+25以控制請求量（56-250宗×26日）。Tier-1（00254/02113）維持全窗。縮窗會漏「事件前30日已建倉」嘅慢建倉形態。
3. **T+90結局對8月中以後公告嘅事件唔存在**（數據只到2026-09-18）：`ret_ann_90`為部分窗（如02113 ret_90=ret_30同值，代表只夠30日數據）。日後重跑`outcomes.py`＋backfill會自動補足。
4. **CCASS快照缺日**（停牌/鏡像缺日）：pivot以ffill處理持有期；缺席=0%先於ffill判定（該日有快照為前提）。
5. **供股事件（200宗）**：供股「額外認購/補償安排」嘅承配人結構同配股差異大，本晚先保證配股500宗；供股批量喺批量隊列尾（fetch_hkex.py --all會一併跑，但驗收以配股為準）。

## 基建注意

1. **webb鏡像cookie**：`checkpoints/webb_cookie.txt`（UA+Cookie兩行）由瀏覽器抽取；失效時fetch_ccass連續3次挑戰失敗會停機＋寫`NEED_COOKIE.flag`，更新後重跑即斷點續傳。
2. **G:虛擬碟Errno 22**：hk_prices_master.csv已複製入`cache/`（44MB），backfill合并喺記憶體做。
3. **ccass-api（Render free）**：冷啟動可達60-120s；`/api/stock` live模式可能逾時——本流程只用佢嘅`/api/stock/price`（Yahoo）同`/health`，都比較穩。

## 驗收狀態（規格§八）

| # | 標準 | 狀態 |
|---|---|---|
| 1 | placees.csv覆蓋≥400/500 | ⏳ 批量進行中（完成後填數） |
| 2 | 30宗抽樣準確率≥90% | ⏳ parser_report.md待批量完成後出 |
| 3 | repeat_placees捉到付尚輝（00254+02113） | ✅ 已驗證 |
| 4 | warehouse_flags標記00254(2026-06)與02113(2026-08/09)為COMBO_BSGS | ✅ 已驗證（00254 peak 12.6%/02113 peak 7.85%） |
| 5 | 全部輸出行皆有source_url | ✅（事件行有；PDF_NO_TEXT/NO_ANN_FOUND行按事實為空＋fail_reason） |
| 6 | Streamlit本機啟動＋姓名搜尋 | ✅（HTTP 200；搜尋邏輯已測） |
| 7 | 中斷後checkpoint恢復 | ✅（事件級/股日級兩級checkpoint，多次實測續跑） |
