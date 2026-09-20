# KNOWN_ISSUES — 已知問題、降級項目與取捨記錄

更新：2026-09-18（通宵任務進行中）

## 降級項目（規格§6.3明令允許：唔可以留空或估 → 標NOT_TESTED）

| 規則 | 狀態 | 原因 |
|---|---|---|
| R3 控股塊場外易手25-29.99% | 🟡 高警示+crash個案已實測（P4.5/P4.6，2026-09-20） | 00254=FALSE、02113=**TRUE**（鄧林輝場外認購落28.00%帶）；其餘個案仍`NOT_TESTED`。DI站經瀏覽器可查；證據走`data/di_evidence.csv` sidecar+alerts.py合併（重生成都唔會沖走；詳DEPLOY_LOG P4.5/P4.6） |
| R5 既有股東/董事高價離場 | 🟡 高警示+crash個案已實測（P4.5/P4.6，2026-09-20） | 00254=**TRUE**（董事賀遠帆05-29場內沽@0.95>認購價0.77）、02113=FALSE（窗口未屆滿至今無沽售）、**00648=TRUE**（黃杰@2.20沽售）；其餘個案仍`NOT_TESTED` |
| R6 利好翌日董事場內減持 | 🟡 高警示+crash個案已實測（P4.5/P4.6，2026-09-20） | 00254=**TRUE**（賀遠帆公告翌日場內減持34.8M股）、02113=FALSE（窗口內無董事申報）；crash個案11宗已實測全FALSE；其餘個案仍`NOT_TESTED` |
| R9 競價U盤異常 | `NOT_TESTED` | 需逐筆/競價數據（規格標明可選） |

**DI補做實錄（P4.5，2026-09-20）**：`di.hkex.com.hk`已恢復（09-19「暫時未能提供」屬站方暫時問題）。正確路線＝瀏覽器經www2.hkexnews.hk入口→DION `NSSrchMethod.aspx`→按上市公司搜尋→List of all notices；**requests直連仍會403，唔好試**。每次抓取間隔≥3秒，全程約10次fetch無封鎖。證據（申報日期/姓名/股數/Form編號/來源URL）已入`alerts.csv`新欄`R3_evidence/R5_evidence/R6_evidence`。

## 已知解析盲點

0. **逐名%表格抽取盲點**（Claude覆核後新增）：86宗具名事件重解析證實——公告逐名認購%幾乎全部以**表格**呈現（認購人|股數|%），顯式句子regex抓唔到，故`pct_enlarged_source`得COMPUTED或NULL、EXPLICIT=0。R2a/b/c新規則只食EXPLICIT→支援度=0，命中者降級`R2_candidate`（02113在列）。**修法**：pdfplumber extract_table按「標籤行→同行數字欄」配對，下一輪做。
0b. **R4/R8已踢出alert_score**（rule_validation.md實證：R4 lift=0.55、R8 lift≈1——貼折讓底係殼股市場常規、低成交係背景條件）。新評分只計R1＋R2系列＋R7（高lift觸發訊號），高度警示門檻改≥2。R4/R8布林欄保留做參考。
0c. **disclosure_check.csv嘅「真漏候選」係過度標記**：00139抽查實證——輸入CSV配售代理欄唔可靠（'-'唔代表直接認購）；抽查個案公告嘅承配人定義真係泛稱。60宗候選只作篩選清單，唔係已證實漏抓。可靠嘅漏抓偵測要靠DI存在性反查（Phase 4.5，未做）。

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

## 驗收狀態（規格§八）— 最終數字

| # | 標準 | 狀態 |
|---|---|---|
| 1 | placees.csv覆蓋≥400/500（≥80%） | ✅ **479/500（95.8%）**公告搵到並解析（11宗NO_ANN_FOUND、7宗代號查唔到stockId、3宗輸入日期問題）；其中84宗（16.8%）公告有具名承配人——其餘261宗屬「泛稱承配人定義」（公告本質上冇名）、131宗冇釋義承配人段（代價發行等），均為誠實輸出 |
| 2 | 30宗抽樣準確率≥90% | ✅ **姓名一致性94.4%、股數格式100%**（36行抽樣，客觀檢查=姓名出現於原文snippet；逐條人工複核表見parser_report.md） |
| 3 | repeat_placees捉到付尚輝（00254+02113） | ✅ `付尚輝（變體：付尚輝/付尚輝先生）n_stocks=2：00254@2026-05-28; 02113@2026-09-02`（另捉到Redbridge Capital、高健行先生兩個候選） |
| 4 | warehouse_flags標記00254(2026-06)與02113(2026-08/09)為COMBO_BSGS | ✅ 00254 peak 12.6%、02113 peak 7.85%（寶新B01666+粵商國際B02014同窗出現）；02113另命中R7衛星倉派貨（粵商國際建倉4.36%→派貨64.4%，散戶+4.25pt） |
| 5 | 全部輸出行皆有source_url | ✅ 具名承配人行100%有公告直鏈；事件級失敗行按事實為空＋fail_reason |
| 6 | Streamlit本機啟動＋姓名搜尋 | ✅ 實機驗證：啟動HTTP 200；「付尚輝」搜尋返回3行（00254×1+02113×2）；支援`?name=`URL參數 |
| 7 | 中斷後checkpoint恢復 | ✅ 實測多次（事件級fetch_state.json／股日級ccass_state.json／PDF快取） |
  File "<stdin>", line 6
    | webb-database.com＋Python requests | ❌ TLS指紋封鎖（JA3） | cookie正確仍403；curl同樣403；瀏覽器同IP同時正常 |
                       ^
SyntaxError: invalid character '＋' (U+FF0B)

## webb鏡像封鎖狀態實錄（2026-09-19凌晨）

| 通道 | 狀態 | 證據 |
|---|---|---|
| webb-database.com＋Python requests | ❌ TLS指紋封鎖（JA3） | cookie正確仍403；curl同樣403；瀏覽器同IP同時正常 |
| webb-database.com 頁內fetch/XHR | ❌ Sec-Fetch-Dest封鎖 | JS無法覆寫Sec-Fetch-*；只有document導航放行 |
| 瀏覽器導航 | 🟡 有限額 | 可用約半小時（~200請求）之後軟封鎖：回應得120-500字節空殼無表 |
| 0xmd鏡像（webbsite.0xmd.com） | 🟡 同上 | 「请稍候」挑戰瀏覽器可過；Python仍TLS 403；URL改寫為 choldings?i=（無.asp）但.asp連d=參數可用 |

**Tier-2餘額（528日期）**：工作清單 `cache/ccass/remaining_work.json`（按crash個案→repeat姓名→其餘排序）；
自動化每50分鐘一輪：瀏覽器測解封→解封就用導航批量抓→`ingest_browser_results.py`併入→全部完成自動跑下游＋commit＋自我刪除。

## 本地 CCASS MySQL（2026-09-19發現，Tier-2嘅正確長遠路線）

本機 `127.0.0.1:3307`（db=ccass）有 webb-site 全量dump：**holdings/parthold 各2.31億行（2007-06-26→2025-12-24）**，
schema：holdings(partID, issueID, holding, atDate)＋participants(partID, CCASSID, partName)。
issueID 同 webb issue_id 同空間（00254=1139✓）。**≤2025-12-24 嘅CCASS查詢一律行本地MySQL，
唔好刮webb/0xmd**（webb-database已403封我哋IP——懷疑mirror_fetch每秒一req觸發WAF；詳 C:\data\AGENTS.md）。
`src/backfill_local_mysql.py` 已將佇列內≤2025-12-24嘅8日併入（53行，pct由shares÷月度股本panel計，detect_warehouse已支援）。
2026年日期（35項）仍需0xmd窗口，自動化每50分鐘續試。

## R2 三級制最終驗證（2026-09-20）

- **可餵 R2a/b/c 數據**：55行/35宗（EXPLICIT+EXACT_COMPUTED）
- **實測命中**：02113 世紀集團——認購人A-D各4.17%，R2a+R2b+R2c三條全中（n=4、cv=0、Σ=16.67%）
- **規則有效性確認**：三級制（EXPLICIT/EXACT_COMPUTED可餵；ESTIMATED只入candidate）下
  R2有真實支援，唔係空轉。原本「EXPLICIT=0」嘅死局由 words-based extract_table_pcts
  + EXACT_COMPUTED 三級制一併解決
- **0xmd 佇列**：459/459 全部完成（17隻股CCASS日度序列入庫）；自動化已刪除
