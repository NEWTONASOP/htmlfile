# Intraday strategy backtests (NSE, yfinance)

One folder per person's strategy, named `NN_<name>_vN/`: NN = order the person came in
(01 first), vN = version of their strategy (a new version is a new folder). Each folder is **self-contained**: nothing is shared
between strategies, so a folder can be copied and run on its own. Every folder has its own
`README.md`, the backtest (`strategy.py`), its own data loader (`data.py`) and an
`indicators/` folder with each indicator as a separate Python file, next to the original
TradingView Pine source where one was provided.

| Strategy | Folder | Timeframe | Indicators |
|---|---|---|---|
| Neeraj – Kyle Algo + Liquidity Swings | [`01_neeraj_v1/`](01_neeraj_v1/README.md) | 5m | Kyle Algo EMA ribbon, Liquidity Swings [LuxAlgo] |
| LAXIT – SMA 20 High/Low + MACD | [`02_laxit_v1/`](02_laxit_v1/README.md) | 2m (5m option) | SMA 20 High/Low, MACD |
| Rakesh Rattan – EMA Crossover | [`03_rakesh_v1/`](03_rakesh_v1/README.md) | 5m | EMA 15/30/35/40/45/50/60 |
| TOUFIK – EMA 4 / MA 10 | [`04_toufik_v1/`](04_toufik_v1/README.md) | 3m | EMA 4, MA 10 (SMA) |
| ASHISHKUMARVERMA – ORB | [`05_ashishkumarverma_v1/`](05_ashishkumarverma_v1/README.md) | 15m | Opening/alert candle, RVOL 20, gap filter, 9 EMA exit |
| AMIT RAJDEV – 5-min Reversal | [`06_amitrajdev_v1/`](06_amitrajdev_v1/README.md) | 5m | SMA 120, LuxAlgo Pivots, Reversal Entry Zones, Smoothed Heiken Ashi |
| PRAFUL – ICT Session Scalper (gold) | [`07_praful_v1/`](07_praful_v1/README.md) | 5m | ICT Session Scalper Toolkit |
| ALIA – OD SOFTWARE (closed-source TradingView strategy, rebuilt) | [`08_alia_v1/`](08_alia_v1/README.md) | 3m | Script's trade signal decoded (EMA 4 × ATR trail 1.7 × ATR 7), stop = closer of 10 pts / 1%, trailing after +20 pts |
| SUNEET – Williams Fractal 7 (NIFTY) | [`09_suneet_v1/`](09_suneet_v1/README.md) | 1m | Williams fractal (Periods 7), CE on red / PE on green arrow, SL arrow wick, reverse on opposite arrow |
| RAJ v1 – MA crossover + Supertrend + RSI (NIFTY ATM options) | [`10_raj_v1/`](10_raj_v1/README.md) | 2m / 5m | SMA 9 × EMA 15 (configurable), Supertrend 10/3, RSI 21 (>60 / <45), 50% at 1:3, trailing SL |
| RAVI v1 – NIFTY ORB (hourly range breakout, ATM options) | [`11_ravi_v1/`](11_ravi_v1/README.md) | 5m | Ranges 09:20/10:00/…/15:00, option VWAP + 9 EMA + ADX, NIFTY 9 EMA, ₹20 SL, 10/10 trailing, 7 EMA exit (Angel One data) |

```
01_neeraj_v1/
  README.md
  strategy.py
  data.py
  indicators/  kyle_algo.py  kyle_algo.pine  liquidity_swings.py  liquidity_swings.pine
02_laxit_v1/
  README.md
  strategy.py
  data.py
  indicators/  sma_bands.py  macd.py  macd.pine
03_rakesh_v1/
  README.md
  strategy.py
  data.py
  indicators/  ema_set.py
04_toufik_v1/
  README.md
  strategy.py
  data.py
  chart.py
  indicators/  ema.py  ma.py
05_ashishkumarverma_v1/
  README.md
  strategy.py
  data.py
  indicators/  orb.py  rvol.py  ema.py
06_amitrajdev_v1/
  README.md
  strategy.py
  data.py
  chart.py
  indicators/  sma.py  luxalgo_pivots.py/.pine  reversal_entry_zones.py/.pine  smoothed_heiken_ashi.py/.pine
07_praful_v1/
  README.md
  strategy.py
  data.py
  indicators/  ict_scalper.py  ict_session_scalper.pine
08_alia_v1/
  README.md
  strategy.py
  data.py
  verify.py
  indicators/  atr_trail.py  dema.py  sma.py   (closed source: no .pine)
  tv_download/ download.mjs  package.json (TradingView export with your account)
09_suneet_v1/
  README.md
  strategy.py
  data.py
  indicators/  williams_fractal.py  williams_fractal.pine
10_raj_v1/
  README.md
  strategy.py
  data.py
  chart.py
  verify.py
  indicators/  moving_averages.py  supertrend.py  rsi.py  + sma/ema/supertrend/rsi .pine
11_ravi_v1/
  README.md
  strategy.py
  data.py      (Angel One, credentials from env)
  chart.py
  verify.py
  indicators/  ema.py  vwap.py  adx.py  + ema/vwap/adx .pine
```

## Run (from the repository root, or `cd <folder>` and `python strategy.py`)

```bash
pip install -r requirements.txt
python 01_neeraj_v1/strategy.py
python 02_laxit_v1/strategy.py
python 03_rakesh_v1/strategy.py
python 04_toufik_v1/strategy.py
python 05_ashishkumarverma_v1/strategy.py
python 06_amitrajdev_v1/strategy.py
python 07_praful_v1/strategy.py
python 08_alia_v1/strategy.py
python 09_suneet_v1/strategy.py
python 10_raj_v1/strategy.py
python 11_ravi_v1/strategy.py --download   # needs ANGEL_* environment variables
```

Both default to `RELIANCE.NS` and the last 5 complete sessions. yfinance keeps about
60 days of intraday history; all of it is downloaded and used as indicator warm-up.

### Google Colab

```
!git clone -q -b claude/kyle-liquidity-swings-strategy-stdnjo https://github.com/NEWTONASOP/htmlfile
%cd htmlfile
!pip install -q yfinance
!python 01_neeraj_v1/strategy.py
!python 02_laxit_v1/strategy.py
!python 03_rakesh_v1/strategy.py
!python 04_toufik_v1/strategy.py
!python 05_ashishkumarverma_v1/strategy.py
!python 06_amitrajdev_v1/strategy.py
!python 08_alia_v1/strategy.py
!python 09_suneet_v1/strategy.py
python 10_raj_v1/strategy.py
```

## Adding a new person's strategy

Create `NN_<name>_vN/` (next number for a new person, next version for a changed strategy) with `README.md`, `strategy.py`, `data.py` and `indicators/<indicator>.py`
(plus the `.pine` source if available). Keep everything inside that folder; do not import
from another strategy.
