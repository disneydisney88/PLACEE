# 00_probe.md — H1 可行性報告（實測可用端點與方法）

日期：2026-09-18 ｜ 執行：zcode ｜ 委託：KL

## 1. 前置資產盤點（全部到位）

| 資產 | 位置 | 規模 |
|---|---|---|
| 配股事件20260831.csv | G:\我的雲端硬碟\STOCKSCAN\data\raw\ | 500宗（已複製入 data/input/） |
| 供股事件20260831.csv | 同上 | 200宗 |
| 全購事件20260831.csv | 同上 | 200宗（本任務僅作背景） |
| 殼股價值分析20260831.csv | 同上 | 1564行 |
| 券商射倉 20251101_20260805.xlsx ×4 | 同上 | 每股一條最新射倉快照（1038隻，非每日序列） |
| hk_prices_master.csv | 同上 | 44MB 日線價格庫（tencent源） |
| shares_outstanding_panel_X0.csv | 同上 | 月度股本（含來源PDF URL） |
| 合股事件/拆股事件20260831.csv | 同上 | 已複製入 data/input/ |
| adj_factors_m1h.csv | G:\我的雲端硬碟\RTSS\zcode\ | 每宗配股攤薄因子（ex_factor） |
| webbsite-ccass-tool（Render API） | https://webbsite-ccass-api.onrender.com | v1.13.0 health OK、Longbridge已認證、Turso後端 |
| 本地 ccass_snapshots.db | ccass_task\ | 52隻股近期快照+價格（覆蓋不足，僅作輔助） |

## 2. HKEX 端點實測（2026-09-18 全部通過）

**Stock ID 解析**（快取入 `checkpoints/stock_ids.json`）：
```
GET https://www1.hkexnews.hk/search/prefix.do?callback=callback&lang=ZH&type=A&name={code}&market=SEHK
→ {"stockInfo":[{"stockId":450,"code":"00254","name":"國家聯合資源"},...]}
```
（注意：回傳含窩輪等同名代號，必須精確匹配5位代號。）

**標題搜尋**：
```
GET https://www1.hkexnews.hk/search/titleSearchServlet.do
    ?sortDir=0&sortByOptions=DateTime&category=0&market=SEHK
    &stockId={sid}&documentType=-1&fromDate={YYYYMMDD}&toDate={YYYYMMDD}
    &title=&searchType=1&t1code=-2&t2Gcode=-2&t2code=-2&rowRange=200&lang=ZH
→ {"result":"[{DATE_TIME,TITLE,FILE_LINK,...}]", "recordCnt":N}
```
FILE_LINK 為相對路徑，PDF 位於 `https://www1.hkexnews.hk{FILE_LINK}`（lang=ZH → `_c.pdf` 中文版）。

**禮貌紀律**：全域請求間隔 ≥1.6秒（單線程）、失敗重試3次指數退避（2/4/8s）、
UA=`hk-placee-registry/1.0 (academic research on HKEX public disclosures; polite crawler)`。
404/410 不重試（公告真係唔存在）。

## 3. PDF 文字抽取：雙引擎策略（關鍵發現）

單一引擎唔可靠，實測發現三類PDF：

| 類型 | 實例 | pdftotext -layout | pdfplumber |
|---|---|---|---|
| 正常 | 00254 認購公告 | ✅ 佳（表格對齊好） | ✅ 可用 |
| **ToUnicode CMap 壞** | 02113 認購公告 | ❌ 全頁亂碼（࠰ಥʿ） | ✅ **完全正常** |
| **雙欄釋義表錯位** | 08245 配售公告 | ❌ 標籤與內容交錯錯配 | ✅ 正確配對 |

**策略**：pdftotext優先（快）→ 質素評分（亂碼字元懲罰 + 「標籤行數 vs 已配對『指』行數」差額懲罰）→
不合格自動轉用 pdfplumber 重抽再比分。掃描圖（文字層<120字元/頁）→ `parse_confidence=LOW`，**唔做OCR**（規格紀律）。

## 4. 釋義解析：10宗試通結果（含兩個必過測試）

| 事件 | 抽取結果 | 判定 |
|---|---|---|
| **00254（2026-05-28認購）** | 第一認購人=鄭凱斌、第二認購人=蒙露芳、**第三認購人=付尚輝** | ✅ 硬測試#3前半命中 |
| **02113（2026-09-02認購）** | 認購人A=**付尚輝**先生、B=游智超先生、C=任開峰先生、D=茹欣銅女士 | ✅ 硬測試#3後半命中（與規格§3.3實例逐字吻合） |
| 00476 | 認購人A-D=金章科技/香港岷壬科技/焰星科技/坤錦控股（公司，實益擁有人另列） | ✅ 公司型承配人 |
| 08079 | 認購方=俊昇香港創意媒體有限公司 | ✅ |
| 01332 | 認購方=彭毅先生 | ✅ |
| 08245 | 「承配人」為泛稱定義（配售代理促成之投資者，公告冇具名） | ✅ 誠實輸出 NO_NAMED_PLACEE |
| 02350 / 01918 | 代價發行（收購賣方取得股份，非承配人） | ✅ 公告搵到，無承配人定義屬事實 |
| 09988 | 公告搵到，冇具名承配人 | ✅ |

**已處理嘅陷阱**：
- 「認購人」群組定義（指認購人A、B及C）唔會誤當第三名承配人（token≥2先判群組）
- 「由王敏女士全資擁有」類body：公司名先出現者為placee，王敏女士入 beneficial_owner（00476教訓）
- 「各認購人將認購40,237,500股」泛稱股數句式 → 套用至全體同類承配人（02113式）
- 02113 有 20:1 合股於 2026-09-14 生效（規格§九.1陷阱實錘）→ Phase 3 必須用調整序列

## 5. 批量規模估算

700宗（配股500＋供股200）×（1 stockId快取 + 1-2次搜尋 + 1-3份PDF下載）× 1.6s/請求
＋解析（pdftotext ~0.1s；pdfplumber後備 ~5-20s/份，估計20-30%觸發）
≈ **2.5–4小時背景運行**，斷點續傳粒度=每宗事件（checkpoints/fetch_state.json）。

## 6. Phase 2 途徑評估（CCASS）

- webbsite-ccass-api `/api/stock?code=` auto模式：優先 webb-site 鏡像（**有完整歷史序列**），
  鏡像403/挑戰時退回 HKEX SDW（單日查詢）。
- 45,000次 SDW 單日查詢（500股×90日）唔可行（>20小時）。
- **計劃**：Tier 1 = 00254/02113 全窗每日（硬測試#4）；Tier 2 = Phase 1 出到具名承配人嘅事件，
  優先 R2 型（多名個人<5%）— 若鏡像可用則每股一次查詢攞全序列，否則縮窗至 D-10..D+30。
- 輔助：本地 ccass_snapshots.db（52隻）＋券商射倉xlsx（快照型，作旁證唔作主證）。

## 7. 結論

可行性確認：端點可用、兩個必過測試喺試通階段已命中、禮貌抓取成本可承受。
風險：掃描版PDF（唔OCR）、供股公告結構差異較大（現阶段優先配股500宗）。
