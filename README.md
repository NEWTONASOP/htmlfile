# Intraday strategy backtests (NSE, yfinance)

One folder per person's strategy. Each folder has its own `README.md`, the backtest
(`strategy.py`) and an `indicators/` folder with each indicator as a separate Python file,
next to the original TradingView Pine source where one was provided.

| Strategy | Folder | Timeframe | Indicators |
|---|---|---|---|
| Neeraj – Kyle Algo + Liquidity Swings | [`neeraj/`](neeraj/README.md) | 5m | Kyle Algo EMA ribbon, Liquidity Swings [LuxAlgo] |
| LAXIT – SMA 20 High/Low + MACD | [`laxit/`](laxit/README.md) | 5m (2m option) | SMA 20 High/Low, MACD |
| Rakesh Rattan – EMA Crossover | [`rakesh/`](rakesh/README.md) | 5m | EMA 15/30/35/40/45/50/60 |

```
common/data.py            shared: yfinance download, CSV loading, IST session cleaning
common/ta.py              shared: Pine-compatible EMA / SMA
neeraj/
  README.md
  strategy.py
  indicators/  kyle_algo.py  kyle_algo.pine  liquidity_swings.py  liquidity_swings.pine
laxit/
  README.md
  strategy.py
  indicators/  sma_bands.py  macd.py  macd.pine
rakesh/
  README.md
  strategy.py
  indicators/  ema_set.py
```

## Run (from the repository root)

```bash
pip install -r requirements.txt
python neeraj/strategy.py
python laxit/strategy.py
python rakesh/strategy.py
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
```

## Adding a new person's strategy

Create `<name>/` with `README.md`, `strategy.py` and `indicators/<indicator>.py`
(plus the `.pine` source if available), and import data from `common.data` (and EMA/SMA from `common.ta`).
