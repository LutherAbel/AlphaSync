# AlphaSync 系統架構

> 本文記錄 **已完成上線** 的系統架構,涵蓋兩大部分:
> 1. **動能輪動策略引擎** (Python) — `python/main.py`
> 2. **策略展示 Web App** (Next.js) — `web/`
>
> 兩者由 `scripts/generate_data.py` 產生的 JSON 快照橋接。本文描述的是 *as-built*(實際落地)的狀態,先前散落在 `docs/superpowers/`(web app 規格與計畫)與 `docs/analysis/`(策略診斷與設計草案)的內容已整併於此。

---

## 1. 系統總覽

```
                  ┌─────────────────────────────────────────┐
                  │  python/main.py                          │
  市場資料 ──────▶│  (自包含動能輪動 + DCA 引擎)              │
  Tiingo / Yahoo  │                                          │
                  └───────────────┬──────────────────────────┘
                                  │ 寫出 CSV
                                  ▼
                  ┌──────────────────────────────────────────┐
                  │  output/  v6dca_*.csv                     │
                  │  (權益曲線 / 交易 / 成交 / regime debug)   │
                  └───────────────┬──────────────────────────┘
                                  │ scripts/generate_data.py
                                  ▼
                  ┌──────────────────────────────────────────┐
                  │  web/data/*.json                          │
                  │  (bars / holdings / trades / executions)  │
                  └───────────────┬──────────────────────────┘
                                  │ import (build-time 靜態資料)
                                  ▼
                  ┌──────────────────────────────────────────┐
                  │  web/  Next.js App                        │
                  │  ┌─ 公開頁:歷史曲線 + 本週持倉           │
                  │  └─ 個人計畫頁:Supabase 登入 + 現金流    │
                  └──────────────────────────────────────────┘
```

**核心設計理念:策略的買賣決策與本金大小無關。** Python 每週只需跑一次,對所有使用者共用同一組週 bar 報酬 (`bar_return`)。每位使用者的個人權益曲線在瀏覽器端,由 `bar_return` + 個人現金流排程即時算出,不需要為每位使用者各跑一次 Python。

---

## 2. 策略引擎架構 (`python/main.py`)

單檔自包含,僅依賴 `numpy / pandas / yfinance`。約 3,000 行,分為以下層次。

### 2.1 資料層

| 元件 | 說明 |
|------|------|
| **資料來源** | 主要 `tiingo`,備援 `yahoo`(`data_provider_primary` / `_fallback`) |
| **本地快取** | `cache/price_cache/`(已移出 output),預設 `price_cache_local_only=True`(離線跑回測;`--allow-network` 才連網) |
| **取樣時間框** | `1d_7d` — 日 K 每 7 天抽樣一根決策 bar;`decision_weekday=2`(週三,休市則順延) |
| **年度快照股池** | `RAW_SNAPSHOTS`:每年 1/1 生效的大型股清單,逐年輪替(2016→2026)。月初往前找最近一筆生效快照,取代固定 `Config.universe` |

### 2.2 引擎層

- **`MomentumEngine`**(基底):動能排名、進出場、regime/macro 閘門、退場掃描。
- **`DCAEngine(MomentumEngine)`**(實際使用):在基底上加入「定期定額」與 TWR 追蹤。
  - 月初定額注資 `monthly_add`(預設 $1,000),初始本金 $10,000。
  - **TWR (Time-Weighted Return)**:注資不改變 NAV,只增加 units,使績效與注資時點脫鉤,可與 SPY 公平比較。

### 2.3 訊號與決策層(state-driven,每根 bar 每檔股票收斂成單一目標狀態)

系統不讓「買進引擎」與「賣出引擎」互相打架。每根 bar、每檔股票解析出唯一目標:
`eligible → base_weight → weight_cap → final_target_weight`,交易只是從現有權重執行到目標權重。

**動能模型**(`--model`,`resolve_momentum_model`):

| 代號 | 名稱 | 說明 |
|------|------|------|
| A | `traditional` | 點對點動能(預設) |
| B | `sharpe` | Sharpe / Information Ratio 風格 |
| C | `clenow` | Clenow 迴歸斜率風格(`clenow_window_weeks=26`) |

**Long sleeve 排名分區**(`momentum_entry_rank=6`, `momentum_hold_rank=8`):

| 區間 | 排名 | 行為 | 基礎權重 |
|------|------|------|----------|
| 進場區 | 1–6 | 可開新倉 | 1–3 名 20% / 4–6 名 10% |
| 持有區 | 7–8 | 只續抱不開新倉 | 5% |
| 出場區 | 9+ | 關倉 | 0% |

正常情況下 long sleeve 最高約 90% gross 多頭曝險(`target_long_total_pct=0.90`)。單檔唯一硬否決是 `initial_stop`(`Close <= stop_price` → 權重歸零);trailing/blowoff/health/conviction 等小型技術退場已從多頭決策堆疊移除,避免與排名持倉決策互打。

**多層風險閘門**(逐層調整目標多頭比例):

1. **Regime Score**(`compute_regime_score`):SPY 趨勢/動能 → sigmoid → 慢速基礎多頭比例 `base_long_pct`(floor 0.20 / ceiling 0.99)。
2. **Cross-sectional Collapse**(`compute_cross_sectional`):前段個股動能與離散度同步崩塌 → 縮減曝險(`cs_early_scale` / `cs_full_scale`)。
3. **VIX 避險閘門**:期限結構倒掛(`VIX/VIX3M > 1.05`)、極端恐慌反向加碼(`contrarian_long_mult`)、Pine hedge(`VIXY`)。
4. **MacroState 雙重鎖(Dual-Gate)逃頂**(`MacroState` / `build_macro_history`):
   - **Shock Warning**(早期警戒):`VIX > VIX3M` 且(`UUP 4W ROC > 3%` 或 `FXY 4W ROC > 4%`)。
   - **Confirmed Regime Deterioration**(開啟長期進場封鎖):`SPY < 20W SMA` 且 `HYG/IEF 12W ROC < -5%` → `long_entry_block_active = True`。
   - **雙重鎖出場**:總經亮紅燈 **且** 大盤跌破均線才清倉;週線觸發時模擬「週內最早日線觸發日」出場,週五另有 safety net 避免漏接。

### 2.4 輸出層

| 檔案(`output/`) | 內容 |
|------|------|
| `v6dca_state.json` | 持倉/現金/last_processed_date,供增量續跑 |
| `v6dca_equity_curve.csv` | 權益曲線(NAV / units / 注資) |
| `v6dca_trades.csv` | 交易紀錄 |
| `v6dca_executions.csv` | 成交明細 |
| `v6dca_regime_debug.csv` | regime / RS gate / CS / VIX / macro 各層診斷(刻意與權益曲線分離,前端不依賴診斷欄位) |

**執行模式**(`--run-mode`):`full`(全量回測、覆寫)/ `incremental`(從 state 續跑、append-only)。`--refresh-web-data` 會接著呼叫 `scripts/generate_data.py` 更新前端資料。

---

## 3. Web App 架構 (`web/`)

Next.js (App Router) + TypeScript,部署於 Vercel。

### 3.1 資料橋接(策略資料以靜態 JSON 注入)

`scripts/generate_data.py` 讀 `output/*.csv` → 產生 `web/data/{bars,holdings,trades,executions}.json` → `web/lib/staticData.ts` 於 build 時 `import` 為靜態常數。**策略歷史資料是打包進前端的快照,非執行期查詢資料庫**,每週重跑策略後重新產生即可。

### 3.2 Supabase(僅用於登入與個人現金流)

- `web/lib/supabase/{client,server}.ts` — Supabase client。
- 用途:**使用者驗證**(`app/auth/callback`、`app/auth/signout`、`lib/useUser.ts`)與 **個人現金流排程**(`user_cashflows`)。
- 策略 bars / holdings **不**走 Supabase,而是上述靜態 JSON。

### 3.3 頁面與元件

| 路由 | 說明 |
|------|------|
| `/` (`app/page.tsx` + `HomePageClient`) | 公開 landing:2016→今的歷史權益曲線、關鍵統計(CAGR / MDD / Sharpe / vs SPY)、本週持倉 |
| `/your-own-plan` | 登入後個人計畫:以個人現金流排程,從今日起投射個人權益曲線 |

**元件**:`EquityChart` / `NavChart` / `CapitalChart`(曲線)、`StatsBar`(統計)、`HoldingsTable` / `TradesTable` / `ExecutionsTable`(表格)、`DateRangePicker` / `RangeButtons`(區間)。

### 3.4 權益曲線計算(client-side,`lib/compute.ts`)

**歷史段(固定參數,所有人相同)**:

```
equity[0] = 10_000
for each bar:                       # is_injection 為真時 inj = 1_000
  equity[t] = (equity[t-1] + inj) * (1 + bar_return)
# SPY 對照曲線用同公式套 spy_return
```

**前進段(登入使用者,個人化)**:起點接歷史段末值(或自選起始金額),`inj` 改為該 bar 的個人現金流總和(recurring / deposit / withdrawal)。CAGR / MDD / Sharpe 由結果序列重算。

---

## 4. 端到端資料流

```
1. main.py 跑策略(full 或 incremental)
        └─▶ output/v6dca_*.csv  (+ state.json)
2. scripts/generate_data.py
        └─▶ web/data/*.json
3. next build:staticData.ts import JSON → 前端靜態資料
4. 瀏覽器:
     公開頁  → 由 bars 還原固定歷史曲線 + 本週 holdings
     個人頁  → Supabase 登入 → 讀 user_cashflows → client-side 投射個人曲線
```

---

## 5. 自動化與儲存佈局

### 5.1 GitHub Actions(兩個 live 排程)

| Workflow | 排程 | 執行 |
|----------|------|------|
| `weekly_web_data_refresh.yml` | 每週五 22:30 UTC | `scripts/generate_data.py` → commit `web/data/` |
| `daily_exit_monitor.yml` | 週一–五 21:30 UTC(NYSE 收盤後) | `python/monitor/daily_exit_monitor.py` |

**每日逃頂監控**是獨立於主回測的 live 守門員:`daily_exit_monitor.py` 載入 `macro_indicators.compute_macro_state` 與 `daily_exit_utils` 的雙重鎖判斷,盤後檢查是否觸發 intra-week 緊急出場,結果寫回 Supabase。這三個檔住在 `python/monitor/`,是現役依賴(此資料夾原名 `deprecated_scripts`,因名不副實已更名)。

### 5.2 儲存佈局(快取與輸出分離)

```
AlphaSync/
├── python/main.py            ← 動能策略引擎(自包含)
│   ├── main_ashare.py        ← 獨立 A 股輪動策略(有測試,與動能產品無關)
│   ├── data/                 ← 輸入資料(macro_signals_historical.csv)
│   └── monitor/              ← 每日逃頂監控 live 三檔(原名 deprecated_scripts)
├── scripts/generate_data.py  ← CSV → web/data JSON
│   └── publish_strategy_run.py  ← 手動 Supabase 發布工具
├── tests/                    ← pytest(32 passed)
├── output/                   ← 策略結果 CSV / state(執行產出)
├── cache/                    ← price_cache/ + yf_tz_cache(可重生,git-ignored)
└── web/                      ← Next.js
```

**路徑慣例**:`main.py` 以 `os.path.dirname(__file__)` + `..` 推導 `output/` 與 `cache/`(main.py 在 `python/` 下,往上一層即 repo root)。快取刻意與 output 分離 —— output 是執行結果、cache 是可重生的下載快取。

---

## 附註:與最初規格的差異

最初的 web app 規格(原 `docs/superpowers/specs/`)設想策略資料經 `export_to_supabase.py` 上傳 Supabase、由 GitHub Actions cron 驅動。實際落地改為更簡單的 **靜態 JSON 快照**(`generate_data.py` → `web/data/*.json`),Supabase 僅保留 **登入 + 個人現金流** 之用;頁面亦由規格的 `/dashboard` + `/settings` 收斂為單一 `/your-own-plan`。本文以實際程式碼為準。
