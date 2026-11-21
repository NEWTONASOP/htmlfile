# AMIT RAJDEV – 5-Minute Reversal Strategy

Intraday backtest on **5-minute** candles that trades only when four indicators agree.
Default: `RELIANCE.NS`, last 5 sessions (one week), quantity 1, data from the unofficial
`yfinance` API (about 60 days of 5-minute history, all used as indicator warm-up).

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: 4-condition entry, 2-condition exit, session rules, report, status |
| `indicators/sma.py` | SMA 120 on close |
| `indicators/luxalgo_pivots.py` / `.pine` | Pivot Points High Low & Missed Reversal Levels [LuxAlgo] (length 50): Python port + original source (© LuxAlgo, CC BY-NC-SA 4.0) |
| `indicators/reversal_entry_zones.py` / `.pine` | Reversal Entry Zones [trade_w_samet] (Low, Average): Python port of the signal engine + original source |
| `indicators/smoothed_heiken_ashi.py` / `.pine` | Smoothed Heiken Ashi Candles v1 (10, 10): Python port + original source |
| `chart.py` | Interactive HTML chart |
| `data.py` | Data loader for this strategy: yfinance 5-minute download, CSV loading, IST session |
| `results/` | Output of the last run: `trades.csv`, `summary.txt`, `bars_with_indicators.csv`, `chart.html` |

## Run

Run from the repository root:

```bash
pip install -r requirements.txt
python amitrajdev/strategy.py                      # RELIANCE.NS, last 5 sessions
python amitrajdev/strategy.py --sessions 40        # about 2 months
python amitrajdev/strategy.py --day 2026-11-17     # print one day's trades
```

## The 4 conditions (checked on every completed 5-minute candle)

| # | Indicator | BUY when | SELL when |
|---|---|---|---|
| 1 | SMA 120 (close) | Close **above** SMA 120 | Close **below** SMA 120 |
| 2 | LuxAlgo pivots (50) | Latest pivot label on the chart (▲ or missed 👻 low) is a **Low** | Latest pivot label (▼ or missed 👻 high) is a **High** |
| 3 | Reversal Entry Zones | Latest label on the chart is **Bullish Reversal** | Latest label is **Bearish Reversal** |
| 4 | Smoothed Heiken Ashi | Candle **Green** | Candle **Red** |

**Notes from the indicator sources**

* **LuxAlgo:** each label (▲/▼ and missed 👻) counts from the candle where it sits on the
  chart. The ghost that moves on the live last candle is provisional and not used.
* **Reversal Entry Zones:** tracks running highs/lows of EMA 5 of high/low. A reversal
  confirms when price comes back by `max(0.015% of close, 0.05, 2.8 × ATR 5)`, and the
  label is drawn at the turning point. The condition changes where that label sits.
* **Smoothed Heiken Ashi:** Red when the smoothed open is above the smoothed close,
  otherwise Green (same as the Pine `col`).

## Rules as implemented

| Item | Implementation |
|---|---|
| Entry | All 4 conditions BUY (or all 4 SELL) on a candle close **and not all 4 on the previous candle** (newly aligned), with no open position → enter at the **next candle open** |
| Re-entry | After an exit, a new entry needs the 4 conditions to newly align again |
| Exit | BUY: exit at the next open when, on a candle close, **2 or more conditions are SELL at that moment** (current state). They do not need to change together, but a condition that has turned back to BUY no longer counts (SELL: 2+ are BUY). The exit reason lists which ones |
| Reverse | No automatic reverse entry after an exit |
| Position | One open position at a time, quantity 1, **no stop loss** |
| Last entry | Entry candle may open at **15:00** at the latest (signal on the 14:55 candle) |
| Square-off | **15:15** (close of the 15:10 candle) |
| Overnight | Indicators run continuously across days, like TradingView, but a signal on the last candle of a day is not carried to the next morning |
| Costs | None by default (`--cost-pct` to add) |
| Signal timing | The LuxAlgo pivot and Reversal Entry Zones conditions change on the candle where their label sits on the chart (pivot candle / turning point), including missed pivots |

## Chart (`results/chart.html`)

* **Top:** 5-minute candles, SMA 120, LuxAlgo pivots (▲/▼ regular, ◇ missed), Reversal
  Entry Zones signals (BULL REV / BEAR REV), BUY/SELL entries and exits (✖, hover shows the reason).
* **Middle:** Smoothed Heiken Ashi candles.
* **Bottom:** status strip of all 4 conditions on every candle (green = BUY, red = SELL).
* **Header:** trade stats and the current BUY/SELL status of each condition.
