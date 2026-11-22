# OD SOFTWARE – the script's own trades + 1% stop and trailing (3-minute, NSE)

Rebuild and backtest of the closed-source, invite-only TradingView strategy
**"Od trading software no wm"** (internal name *OD SOFTWARE*, by mahaprasadnayak12345,
[tradingview.com/v/SQYvrxuA](https://in.tradingview.com/v/SQYvrxuA/), script id
`PUB;bd646e96ec1548949f18d637a39a7d20`). The Pine code is hidden, so the logic was decoded
from the script's own outputs (inputs, plotted lines, arrows, Strategy-Tester trades),
downloaded with a TradingView account that has access, and every piece was checked against them.

The backtest takes **the script's own entries** (same as its trades on the chart) and adds the
client's exits: a 1% stop and a trailing stop after the target.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: the script's signal, reversals, 10-pt / 1% stop, trailing after +20 pts, report |
| `indicators/atr_trail.py` | The script's **trade signal**: ATR trailing stop on EMA 4 of close (1.7 × ATR 7) |
| `indicators/dema.py` | Chart line "Fast MA": DEMA 20 on close (Pine `ta.dema`) |
| `indicators/sma.py` | Chart line "Trend MA line": SMA 40 on close (Pine `ta.sma`) |
| `data.py` | Data loader: yfinance 1m → 3m candles, or a CSV (the TradingView export) |
| `verify.py` | Checks the rebuild against TradingView: lines, arrows, and a replay of the script's own trades |
| `tv_download/download.mjs` | Downloads candles, the script's lines/arrows and its Strategy-Tester trades with your account |
| `data/` | TradingView exports (gitignored) |
| `results/` | Output of the last run: `trades.csv`, `summary.txt`, `bars_with_indicators.csv` (gitignored) |

There is no `.pine` file: the script is closed source.

## What the script does (decoded)

### Its trades (Strategy Tester and the trade marks on the chart)

| Part | Decoded as |
|---|---|
| Signal line | **EMA 4 of close** (input `st_emaPer` 4) |
| Trail | ATR trailing stop on that EMA, **1.7 × ATR 7** away (inputs `st_factor` 1.7, `TrPer` 7; `ta.atr`) |
| BUY / SELL | EMA crosses **above / below** the trail; they always alternate → enter at the next candle's open |
| Exit | **Stop 10 points, target 20 points** (Trade Mode "Point"), working from the candle after entry; the opposite signal **reverses** the trade |
| Session | none: trades are held overnight |

Formula (`indicators/atr_trail.py`): `trail = src > trail[1] and src[1] > trail[1] ? max(trail[1],
src − nLoss) : src < trail[1] and src[1] < trail[1] ? min(trail[1], src + nLoss) : src > trail[1] ?
src − nLoss : src + nLoss`, with `src = ema(close, 4)` and `nLoss = 1.7 × atr(7)`.

Checks against the TradingView trade lists (3-minute, 21 Sep – 20 Nov 2026), same entry candle,
side, exit candle and exit reason:

| Symbol | TradingView trades | Identical in the Python replay | Differences |
|---|---|---|---|
| NIFTY | 152 | **152** | none |
| RELIANCE | 163 | **163** | 1 extra Python trade (7 Oct 09:18) |
| SBIN | 146 | **146** | 1 extra Python trade (5 Nov 09:18) |
| HDFCBANK | 159 | **155** | 13 Oct open and 17 Nov morning |
| **Total** | **620** | **616 (99.4%)** | |

The few differences are all on stocks, where TradingView keeps issuing "Margin call" partial
closes (40–72 per stock) because of the script's position sizing; around some of them TradingView
skips or changes a trade. NIFTY has no margin calls and matches completely.
Changing every input on TradingView one at a time showed that only `st_emaPer`, `TrPer` and
`st_factor` move the trades (the MAs, the OD inputs and smoothing don't); with TrPer 14 the
Python replay matched all 150 trades, with st_factor 3 81 of 82, with st_emaPer 8 105 of 108
(misses where the EMA and the trail were within a few points).

### Its lines and arrows (display only, not used for trades)

| Part | Decoded as | Check |
|---|---|---|
| "Trend MA line" | SMA 40 of close | identical (max difference 0.000000) |
| "Fast MA" | DEMA 20 of close | identical (max difference 0.000000) |
| BUY / SELL arrows | DEMA 20 crosses above / below SMA 40 | NIFTY 119/119, RELIANCE 122/122, HDFCBANK 138/138, SBIN 144/144 |

Only 40 of the 152 NIFTY trades start at an arrow: the arrows are not the trade signal. The
"OD" band (22, × 2), bar colours, screener table, pivots and day high/low don't affect trades.

## Rules as implemented (backtest)

| Item | Implementation |
|---|---|
| Timeframe | 3-minute candles, IST. Default NIFTY 50 (`^NSEI`); stocks with `--symbol RELIANCE.NS --qty <shares>` |
| BUY / SELL | The script's signal (EMA 4 crosses above / below the ATR trail) on a closed candle → **next candle's open**. Entries are the same as the script's trades on TradingView |
| Reversal | The opposite signal exits the open trade and enters the other side at the same open. One position at a time |
| Stop loss | **Whichever is closer to entry: 10 points (the script's stop) or 1%**. NIFTY and RELIANCE: 10 points; HDFCBANK: 1%; SBIN: either, depending on price |
| Target → trailing | At **+20 points** (the script's target) the trade is **not** booked: the stop moves to entry (breakeven) and then trails **1% behind the best price** (highest high for BUY, lowest low for SELL). It only tightens |
| Exit | Whichever comes first: stop, breakeven/trailing stop, opposite signal (reverse) |
| Session | **None, like the script**: trades are held overnight. A trade still open when the data ends is closed at the last close ("Open at end") |
| Fills | Signal on the candle close, fill at the next open. Stops and target tracking start on the candle after entry, like the script's exit orders. A stop moved by a candle's high/low is used from the next candle. A gap through the stop fills at the open |
| Warm-up | Signals only after 120 candles |
| Quantity / costs | `--qty` (default **65**, NIFTY lot) and `--cost-pct` round trip (default 0). P&L = points × qty (index points are a proxy for futures). The script's own position sizing is not copied |

Note for NIFTY: 1% is about 250 points, so after +20 points the stop stays at breakeven until
price has moved more than 1% in the trade's favour; most such trades end at breakeven or on the
opposite signal. On stocks 1% is close to 10–20 points, so the trail moves with price.

## Data

| Source | Use | Notes |
|---|---|---|
| TradingView export (`--csv odsoftware/data/NSE_NIFTY_3.csv`) | **Matches the client's chart exactly** | About 2 months of 3-minute history (5,059 candles on a free plan). Needs the downloader below |
| yfinance `^NSEI` / `RELIANCE.NS` (default) | No login needed | 1-minute candles grouped into 3-minute (09:15, 09:18, …); only about the last 30 days (≈ 18–20 sessions) |

- **Session end 15:15:** TradingView's NSE 3-minute data (NIFTY and stocks) stops at 15:15 (last
  candle 15:12); Yahoo continues to 15:29. The extra Yahoo candles change the indicators, so
  candles from 15:15 on are dropped. With that, Yahoo reproduces 47 of 48 NIFTY arrows and 62 of
  63 RELIANCE arrows (Yahoo RELIANCE closes equal TradingView's on every candle checked).
- **Muhurat session** (Sun 8 Nov 2026, 19 candles on TradingView's own grid): Yahoo doesn't have
  it, which causes the one difference left on the next morning. A 3-minute CSV is used as it is.
- Use the TradingView export for chart-exact results.

## Run

From the repository root:

```bash
pip install -r requirements.txt
python odsoftware/strategy.py                                            # ^NSEI from yfinance, last 20 sessions
python odsoftware/strategy.py --csv odsoftware/data/NSE_NIFTY_3.csv --sessions 60   # TradingView candles
python odsoftware/strategy.py --symbol RELIANCE.NS --qty 100              # a stock
python odsoftware/strategy.py --day 2026-11-17                           # print one day's trades
python odsoftware/verify.py odsoftware/data/NSE_NIFTY_3.csv --yahoo      # rebuild vs TradingView
python odsoftware/verify.py odsoftware/data/NSE_RELIANCE_3.csv --yahoo --symbol RELIANCE.NS
```

## Comparing with the TradingView chart

- **Entries** (time and side) are the same as the script's trades on the chart: the "Long" /
  "Short" entry marks its Strategy Tester draws (not the BUY/SELL arrows). Chart settings:
  3-minute, regular session, script inputs at default.
- **Exits differ on purpose**: the chart books at 20 points and stops at 10 points; this backtest
  uses the closer of 10 points / 1% and trails after 20 points. `verify.py` replays the script's
  exact trades if you want to check them one by one against the chart.
- Signals use closed candles. On a live, still-forming candle the EMA can cross the trail and
  cross back, so a signal may show and vanish before the candle closes.

## TradingView downloader

Uses the unofficial [TradingView-API](https://github.com/Mathieu2301/TradingView-API)
(`@mathieuc/tradingview` 4.1.2, Node ≥ 20). The account must have access to the invite-only
script. Login is by **session cookies**: TradingView blocks password login from servers.

1. Log in at tradingview.com in Chrome → DevTools (F12) → Application → Cookies →
   `https://www.tradingview.com` → copy `sessionid` and `sessionid_sign`.
2. Put them in environment variables, **never in a file or a commit**:

```bash
export TV_SESSION='...sessionid...'
export TV_SIGNATURE='...sessionid_sign...'
```

```bash
npm --prefix odsoftware/tv_download install
```

```bash
node odsoftware/tv_download/download.mjs NSE:NIFTY 3 6000
```

This writes `odsoftware/data/NSE_NIFTY_3.csv` (candles + the script's Fast MA, Trend MA line,
BUY/SELL arrows) and `NSE_NIFTY_3_tv_trades.csv` (the script's Strategy-Tester trades). Notes:

- The cookies give full access to that TradingView account. Log out of all sessions on
  TradingView when done to invalidate them.
- TradingView's site answers 403 to the library without a browser user agent, so the downloader
  sends a Chrome user agent.
- The script's 30-stock screener table makes a free-plan account fail with `symbol_not_auth`; the
  downloader switches the table off and points its symbols at `OANDA:XAUUSD`. The table is display
  only and does not affect lines, arrows or trades.
- Free plan: NSE data is delayed and history stops at about 5,000 candles.
- In a cloud sandbox the downloader uses `HTTPS_PROXY` and `NODE_EXTRA_CA_CERTS`; on a normal
  PC it connects directly.

## Verified

- **Entries:** the backtest's entries equal the script's TradingView entries after warm-up on
  NIFTY 149/149, RELIANCE 161/161, SBIN 144/144, HDFCBANK 153/155; 3 extra entries in total, all at
  TradingView margin-call moments on stocks.
- **Exits:** the trade engine was compared with a separately written simulator (per-trade forward
  scan, trailing stop recomputed from the running high/low) on all four symbols and a forced
  gap-through-stop case: **identical trades** in every case. Invariants checked: entry = next open
  after a signal of that side, no overlap, no exit on the entry candle, initial stop = closer of
  10 points / 1%, trailing only after +20 points.
- One trailing trade checked candle by candle (SBIN BUY 16 Oct 15:03 at 959.70: stop 950.10 = 1%,
  held overnight, +20 points reached 19 Oct 09:36, stop trailed 1% behind the high to 973.96, exit
  10:36).
- `verify.py`: script lines identical (0.000000), arrows identical, script trades replayed
  (NIFTY 152/152).
