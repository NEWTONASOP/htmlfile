# OD SOFTWARE – DEMA 20 / SMA 40 arrows (NIFTY 3-minute)

Rebuild and backtest of the closed-source, invite-only TradingView strategy
**"Od trading software no wm"** (internal name *OD SOFTWARE*, by mahaprasadnayak12345,
[tradingview.com/v/SQYvrxuA](https://in.tradingview.com/v/SQYvrxuA/), script id
`PUB;bd646e96ec1548949f18d637a39a7d20`). The Pine code is hidden, so the logic was decoded
from the script's own outputs (inputs, plotted lines, arrows), downloaded with a TradingView
account that has access, and every piece was checked against those outputs.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: arrow entries, reversals, 1% SL, trailing SL after +1%, square-off, report |
| `indicators/dema.py` | Fast MA: DEMA 20 on close (Pine `ta.dema`, SMA-seeded `ta.ema`) |
| `indicators/sma.py` | Slow / trend MA: SMA 40 on close (Pine `ta.sma`) |
| `indicators/atr_trail.py` | The script's **trade signal**: ATR trailing stop on EMA 4 of close (ATR 7 × 1.7) |
| `data.py` | Data loader: yfinance 1m → 3m candles, or a CSV (the TradingView export) |
| `verify.py` | Checks the rebuild against TradingView's plotted lines and arrows (and optionally Yahoo) |
| `tv_download/download.mjs` | Downloads candles, the script's lines/arrows and its Strategy-Tester trades from TradingView with your account |
| `data/` | TradingView exports (gitignored) |
| `results/` | Output of the last run: `trades.csv`, `summary.txt`, `bars_with_indicators.csv` (gitignored) |

There is no `.pine` file: the script is closed source.

## What the indicator is (decoded)

| Part | Decoded as | Check against TradingView (NSE:NIFTY 3m, 21 Sep – 20 Nov 2026, 5,059 candles) |
|---|---|---|
| Slow MA ("Trend MA line") | **SMA 40 of close** | identical (max difference 0.000000) |
| Fast MA ("Fast MA") | **DEMA 20 of close** | identical (max difference 0.000000) |
| **BUY arrow** | **DEMA 20 crosses above SMA 40** on a closed candle | 60 of 60 |
| **SELL arrow** | **DEMA 20 crosses below SMA 40** on a closed candle | 59 of 59 after warm-up |
| | | **119 / 119 arrows, 0 missed, 0 extra** |

Also checked on **NSE:RELIANCE 3m** (same period): lines identical, **122 / 122 arrows**.

The script's settings say the same: Slow MA 40 SMA, Fast MA 20 DEMA, both on close, smoothing
off. The other parts of the script do **not** change the arrows: a Supertrend-style trail
(EMA 4, TR 7, factor 1.7), an "OD" band (22, factor 2), bar colours, a 30-stock screener
table, pivots and day high/low.

### The script's own trades (Strategy Tester) – decoded too

The trades the script draws on the chart and lists in its Strategy Tester do **not** come
from the arrows (only 40 of 152 start at an arrow). They come from a separate signal:

| Part | Decoded as |
|---|---|
| Signal line | **EMA 4 of close** (input `st_emaPer` 4) |
| Trail | ATR trailing stop on that EMA: distance **1.7 × ATR 7** (inputs `st_factor` 1.7, `TrPer` 7; ATR = `ta.atr`) |
| BUY / SELL | EMA crosses **above / below** the trail (they always alternate) → enter at the next candle's open |
| Exit | **Stop 10 points, target 20 points** from entry (Trade Mode "Point"), active from the candle after entry; an opposite signal **reverses** the trade |
| Session | none: trades are held overnight |

Checks: on NSE:NIFTY 3m the Python replay gives **all 152 TradingView trades identically**
(entry candle, side, exit candle, exit reason). On NSE:RELIANCE 3m it gives all 163
TradingView trades plus one extra (7 Oct 09:18 SELL, right after an overnight stop-loss);
TradingView also splits 40 RELIANCE trades with "Margin call" rows caused by the script's
position sizing, most likely also why it skipped that trade. Changing every input on
TradingView one at a time showed that only `st_emaPer`, `TrPer` and `st_factor` move the
trades (the MAs, the OD inputs and smoothing don't); with TrPer 14 the Python replay matched all
150 trades, with st_factor 3 81 of 82 and with st_emaPer 8 105 of 108 (the misses are candles
where the EMA and trail were within a few points).

The backtest in `strategy.py` uses the client's rules on the **arrows** (below), not the
script's trade signal.

## Rules as implemented

| Item | Implementation |
|---|---|
| Timeframe | 3-minute candles, IST. Default NIFTY 50 index (`NSE:NIFTY` / `^NSEI`); NSE stocks with `--symbol RELIANCE.NS --qty <shares>` |
| BUY | BUY arrow (DEMA 20 crosses **above** SMA 40) on a closed candle → buy at the **next candle's open** |
| SELL | SELL arrow (DEMA 20 crosses **below** SMA 40) → sell (short) at the next candle's open |
| Reversal | An opposite arrow exits the open trade and enters the other side at the same open. One position at a time |
| Stop loss | **1%** from entry (BUY below, SELL above), checked on each candle's low/high |
| Trailing SL | When price reaches **+1%** (target, 1:1), the stop moves to **entry (breakeven)** and then **trails 1% behind the best price** reached (highest high for BUY, lowest low for SELL). It only tightens |
| Exit | Whichever comes first: 1% SL, breakeven/trailing SL, opposite arrow, 15:15 square-off. After a stop exit, wait for the next arrow |
| Session | Entries only on candles opening **before 15:00**; anything open is squared off at **15:15** (close of the 15:12 candle). Nothing carried overnight; an arrow on the day's last candles is not used |
| Fills | Signal on the candle close, fill at the next open. If one candle touches both the stop and the +1% level, the **stop counts first**. A stop moved by a candle's high/low is used from the next candle. A gap through the stop fills at that candle's open |
| Warm-up | Signals only after 120 candles so the SMA/DEMA have settled |
| Quantity / costs | `--qty` (default **65**, NIFTY lot) and `--cost-pct` round trip (default 0). P&L is index points × qty: a proxy for futures; option premiums are not modelled |

Assumed (not specified by the client): the 15:00 last-entry time.

## Data

| Source | Use | Notes |
|---|---|---|
| TradingView export (`--csv odsoftware/data/NSE_NIFTY_3.csv`) | **Matches the client's chart exactly** | About 2 months of 3-minute history (5,059 candles on a free plan). Needs the downloader below |
| yfinance `^NSEI` (default) | No login needed | 1-minute candles grouped into 3-minute (09:15, 09:18, …); only about the last 30 days (≈ 18–20 sessions) |

- **Session end 15:15:** TradingView's NSE:NIFTY 3-minute data stops at 15:15 (last candle
  15:12, 120 candles a day); Yahoo continues to 15:29. The extra Yahoo candles shift the
  SMA/DEMA, so candles from 15:15 on are dropped. With that, Yahoo reproduces **47 of 48**
  TradingView arrows over 27 Oct – 20 Nov 2026.
- RELIANCE: TradingView's 3-minute data also stops at 15:15. Yahoo `RELIANCE.NS` closes equal
  TradingView's on every candle checked (2,160) and reproduce **62 of 63** arrows.
- **Muhurat session** (Sun 8 Nov 2026, 19 candles on TradingView's own grid): Yahoo doesn't
  have it, which is the one arrow difference left on both symbols (9 Nov morning). A 3-minute CSV is used as it
  is, so the TradingView candles stay exactly as on the chart.
- Yahoo prices differ slightly from TradingView (opens of the 09:15 candle by up to ±16 points),
  so an arrow decided by a few points can differ. Use the TradingView export for chart-exact
  results.

## Run

From the repository root:

```bash
pip install -r requirements.txt
python odsoftware/strategy.py                                           # ^NSEI from yfinance, last 20 sessions
python odsoftware/strategy.py --csv odsoftware/data/NSE_NIFTY_3.csv --sessions 60   # TradingView candles
python odsoftware/strategy.py --qty 65 --cost-pct 0.02
python odsoftware/strategy.py --day 2026-11-17                          # print one day's trades
python odsoftware/verify.py odsoftware/data/NSE_NIFTY_3.csv --yahoo     # check rebuild vs TradingView
python odsoftware/strategy.py --symbol RELIANCE.NS --qty 100             # a stock
python odsoftware/verify.py odsoftware/data/NSE_RELIANCE_3.csv --yahoo --symbol RELIANCE.NS
```

## Comparing with the TradingView chart

Compare the **arrows**, not the script's Strategy Tester list (that uses the script's own
10/20-point exits and other entries, see above). On the chart: 3-minute timeframe, regular
session, script inputs left at default (Fast MA 20 DEMA, Slow MA 40 SMA). The arrow sits on the
crossover candle; this backtest's entry is the **next** candle's open (arrow time + 3 minutes).
Our arrows use closed candles only: on a live, still-forming candle the DEMA can cross and
uncross, so an arrow may show and vanish before that candle closes.

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
  only and does not affect the lines or arrows.
- Free plan: NSE data is delayed and history stops at about 5,000 candles.
- In a cloud sandbox the downloader uses `HTTPS_PROXY` and `NODE_EXTRA_CA_CERTS`; on a normal
  PC it connects directly.

## Verified

- Python SMA 40 / DEMA 20 equal the script's plotted lines (difference 0.000000) and the Python
  arrows equal all 119 TradingView arrows (`verify.py`).
- `verify.py` also replays the script's own trades (ATR-trail entries, 10/20-point exits) and
  compares them with the downloaded `_tv_trades.csv`: NIFTY 152 / 152 identical.
- The trade engine was compared with a separately written simulator (per-trade forward scan,
  trailing stop recomputed from the running high/low) on 4 synthetic datasets, a forced
  gap-through-stop case and the TradingView NIFTY data: **identical trades** in all cases.
  Invariants checked: entry = next candle's open after an arrow of that side, no overlap, no
  entry from 15:00, no overnight, square-off on the 15:12 candle, 1% SL price, trailing only
  after +1%.
- One trailing trade checked candle by candle (SELL 8 Oct 2026: +1% reached at 12:18, stop
  trailed 1% above the lowest low, squared off at 15:12).
- On NIFTY 3m the 1% stop was never reached in the tested period (largest move against a trade
  0.68%), and the 4 trades that reached +1% ended by square-off or an opposite arrow before the
  trailing stop was hit: in this period the exits came from the arrows and 15:15.
