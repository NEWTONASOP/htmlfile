# LAXIT – Intraday Strategy

Intraday backtest on 2-minute candles (5-minute with `--interval 5m`) using SMA 20 High,
SMA 20 Low and MACD. Default: `RELIANCE.NS`, last 1 week (5 sessions), data from `yfinance`.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: setups, entries, stop loss, 50% booking, trailing, report |
| `indicators/sma_bands.py` | SMA 20 of High and SMA 20 of Low (simple, `ta.sma`) |
| `indicators/macd.py` | MACD 12/26/9 and crossovers (Python port of the built-in) |
| `indicators/macd.pine` | TradingView built-in MACD Pine source |
| `data.py` | Data loader for this strategy: yfinance download, CSV loading, IST session |
| `results/` | Output of the last run (created when you run it) |

## Run

Run from the repository root:

```bash
python laxit/strategy.py                  # RELIANCE.NS 2m, last 5 complete sessions
python laxit/strategy.py --interval 5m    # same rules on 5-minute candles
python laxit/strategy.py --sessions 40 --cost-pct 0.05
python laxit/strategy.py --day 2026-11-13 # print one day's trades
python laxit/strategy.py --one-at-a-time  # no CALL/PUT overlap
```

Outputs go to `laxit/results/`. MACD follows the TradingView built-in source: EMA 12 − EMA 26
of close, signal = EMA 9 of MACD (EMAs seeded like Pine's `ta.ema`). A crossover is the
histogram crossing 0.

## Rules as implemented

| Item | Implementation |
|---|---|
| Timeframe | 2-minute candles (`--interval 5m` for 5-minute) |
| Indicators | SMA 20 of High, SMA 20 of Low, MACD 12/26/9 on close |
| CALL setup candle | Green, **more than 50% of its body above SMA 20 High**, and a **bullish MACD crossover** (MACD crossing above its signal line) on this candle or the 2 candles before it, with MACD still above signal |
| PUT setup candle | Red, more than 50% of its body below SMA 20 Low, and a bearish crossover on this candle or the 2 before it, with MACD still below signal |
| Entry | **Next candle only**: CALL fills when price breaks above the setup high (at the open if it gaps above it). PUT fills on a break below the setup low |
| Trading time | Entry candle between 09:45 and 14:20 (last 2m entry candle 14:18–14:20). Trades already open are held until 15:15 |
| Stop loss | CALL: SMA 20 Low on the setup candle. PUT: SMA 20 High. Fixed until T1 |
| T1 | 1:1 of the initial risk: book **50%** and move SL to **cost** |
| Trail | After T1, at each candle close the SL follows SMA 20 Low (CALL) or SMA 20 High (PUT), only ever tightening and never past cost |
| Exit | SL / cost / trailing SL, otherwise squared off at 15:15 |
| Same candle hits SL and target | SL counted first (conservative) |
| Qualifying vs entry candle | The **qualifying (setup) candle** is the one with 50%+ of its body beyond the SMA and the MACD crossover. The **entry candle** is the next one, which must break the setup candle's high (CALL) or low (PUT). `setup_time` and `entry_time` in the output |
| CALL vs PUT | Independent trades, one open per side (`--one-at-a-time` allows a single position) |
| P&L | Per share: 50% at T1 + 50% at the final exit (100% at the SL if T1 was never reached) |
