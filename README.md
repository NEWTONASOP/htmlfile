# Intraday strategy backtests (NSE, yfinance)

One folder per person's strategy. Each folder is **self-contained**: nothing is shared
between strategies, so a folder can be copied and run on its own. Every folder has its own
`README.md`, the backtest (`strategy.py`), its own data loader (`data.py`) and an
`indicators/` folder with each indicator as a separate Python file, next to the original
TradingView Pine source where one was provided.

| Strategy | Folder | Timeframe | Indicators |
|---|---|---|---|
| Neeraj – Kyle Algo + Liquidity Swings | [`neeraj/`](neeraj/README.md) | 5m | Kyle Algo EMA ribbon, Liquidity Swings [LuxAlgo] |
| LAXIT – SMA 20 High/Low + MACD | [`laxit/`](laxit/README.md) | 5m (2m option) | SMA 20 High/Low, MACD |
| Rakesh Rattan – EMA Crossover | [`rakesh/`](rakesh/README.md) | 5m | EMA 15/30/35/40/45/50/60 |
| TOUFIK – EMA 4 / MA 10 | [`toufik/`](toufik/README.md) | 3m | EMA 4, MA 10 (SMA) |
| ASHISHKUMARVERMA – ORB | [`ashishkumarverma/`](ashishkumarverma/README.md) | 15m levels, 1m breakout | ORB candle, alert candle |

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
  indicators/  orb.py
```

## Run (from the repository root, or `cd <folder>` and `python strategy.py`)

```bash
pip install -r requirements.txt
python neeraj/strategy.py
python laxit/strategy.py
python rakesh/strategy.py
python toufik/strategy.py
python ashishkumarverma/strategy.py
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
```

## Adding a new person's strategy

Create `<name>/` with `README.md`, `strategy.py`, `data.py` and `indicators/<indicator>.py`
(plus the `.pine` source if available). Keep everything inside that folder; do not import
from another strategy.
