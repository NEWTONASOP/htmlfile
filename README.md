# Intraday strategy backtests (NSE, yfinance)

One folder per person's strategy. Each folder is **self-contained**: nothing is shared
between strategies, so a folder can be copied and run on its own. Every folder has its own
`README.md`, the backtest (`strategy.py`), its own data loader (`data.py`) and an
`indicators/` folder with each indicator as a separate Python file, next to the original
TradingView Pine source where one was provided.

| Strategy | Folder | Timeframe | Indicators |
|---|---|---|---|
| Neeraj – Kyle Algo + Liquidity Swings | [`neeraj/`](neeraj/README.md) | 5m | Kyle Algo EMA ribbon, Liquidity Swings [LuxAlgo] |
| LAXIT – SMA 20 High/Low + MACD | [`laxit/`](laxit/README.md) | 2m (5m option) | SMA 20 High/Low, MACD |
| Rakesh Rattan – EMA Crossover | [`rakesh/`](rakesh/README.md) | 5m | EMA 15/30/35/40/45/50/60 |
| TOUFIK – EMA 4 / MA 10 | [`toufik/`](toufik/README.md) | 3m | EMA 4, MA 10 (SMA) |
| ASHISHKUMARVERMA – ORB | [`ashishkumarverma/`](ashishkumarverma/README.md) | 15m | Opening/alert candle, RVOL 20, gap filter, 9 EMA exit |
| AMIT RAJDEV – 5-min Reversal | [`amitrajdev/`](amitrajdev/README.md) | 5m | SMA 120, LuxAlgo Pivots, Reversal Entry Zones, Smoothed Heiken Ashi |
| PRAFUL – ICT Session Scalper (gold) | [`praful/`](praful/README.md) | 5m | ICT Session Scalper Toolkit |
| ALIA – OD SOFTWARE (closed-source TradingView strategy, rebuilt) | [`alia/`](alia/README.md) | 3m | Script's trade signal decoded (EMA 4 × ATR trail 1.7 × ATR 7), stop = closer of 10 pts / 1%, trailing after +20 pts |
| SUNEET – Williams Fractal 7 (NIFTY) | [`suneet/`](suneet/README.md) | 1m | Williams fractal (Periods 7), CE on red / PE on green arrow, SL arrow wick, reverse on opposite arrow |

```
neeraj/
  README.md
  strategy.py
  data.py
  indicators/  kyle_algo.py  kyle_algo.pine  liquidity_swings.py  liquidity_swings.pine
laxit/
  README.md
  strategy.py
  data.py
  indicators/  sma_bands.py  macd.py  macd.pine
rakesh/
  README.md
  strategy.py
  data.py
  indicators/  ema_set.py
toufik/
  README.md
  strategy.py
  data.py
  chart.py
  indicators/  ema.py  ma.py
ashishkumarverma/
  README.md
  strategy.py
  data.py
  indicators/  orb.py  rvol.py  ema.py
amitrajdev/
  README.md
  strategy.py
  data.py
  chart.py
  indicators/  sma.py  luxalgo_pivots.py/.pine  reversal_entry_zones.py/.pine  smoothed_heiken_ashi.py/.pine
praful/
  README.md
  strategy.py
  data.py
  indicators/  ict_scalper.py  ict_session_scalper.pine
alia/
  README.md
  strategy.py
  data.py
  verify.py
  indicators/  atr_trail.py  dema.py  sma.py   (closed source: no .pine)
  tv_download/ download.mjs  package.json (TradingView export with your account)
suneet/
  README.md
  strategy.py
  data.py
  indicators/  williams_fractal.py  williams_fractal.pine
```

## Run (from the repository root, or `cd <folder>` and `python strategy.py`)

```bash
pip install -r requirements.txt
python neeraj/strategy.py
python laxit/strategy.py
python rakesh/strategy.py
python toufik/strategy.py
python ashishkumarverma/strategy.py
python amitrajdev/strategy.py
python praful/strategy.py
python alia/strategy.py
python suneet/strategy.py
```

Both default to `RELIANCE.NS` and the last 5 complete sessions. yfinance keeps about
60 days of intraday history; all of it is downloaded and used as indicator warm-up.

### Google Colab

```
!git clone -q -b claude/kyle-liquidity-swings-strategy-stdnjo https://github.com/NEWTONASOP/htmlfile
%cd htmlfile
!pip install -q yfinance
!python neeraj/strategy.py
!python laxit/strategy.py
!python rakesh/strategy.py
!python toufik/strategy.py
!python ashishkumarverma/strategy.py
!python amitrajdev/strategy.py
!python alia/strategy.py
!python suneet/strategy.py
```

## Adding a new person's strategy

Create `<name>/` with `README.md`, `strategy.py`, `data.py` and `indicators/<indicator>.py`
(plus the `.pine` source if available). Keep everything inside that folder; do not import
from another strategy.
