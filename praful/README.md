# PRAFUL – ICT Session Scalper on Gold

Gold scalping on **5-minute** candles with the **ICT Session Scalper Toolkit** signals,
a **+$3 take profit** per trade (0.01 lot), and exits on liquidity sweeps. Data: COMEX gold
futures `GC=F` from Yahoo (no spot XAUUSD on Yahoo), about the last 60 days, New York time.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: takes the indicator's signals, simulates each trade, report |
| `indicators/ict_scalper.py` | Python port of the indicator's signal engine (sessions, liquidity pools, sweeps, displacement, FVG/IFVG, 1H/daily FVGs, MOP/NDOG/NWOG, premium/discount, SMT, signals and grading) |
| `indicators/ict_session_scalper.pine` | Original Pine source of the ICT Session Scalper Toolkit |
| `data.py` | Data loader: Yahoo 5-minute futures candles in New York time |
| `results/` | Output of the last run: `trades.csv`, `summary.txt` |

## Run

```bash
pip install -r requirements.txt
python praful/strategy.py
```

## Rules as implemented

| Item | Implementation |
|---|---|
| Market | Gold, COMEX futures `GC=F` (moves almost the same as spot XAUUSD); tick 0.10 |
| Timeframe | 5 minutes; all session logic in New York time |
| Signal (BUY) | The indicator's **▲ LONG**: a sellside liquidity pool is swept (✗), then a displacement candle up, then price taps a bullish FVG or a bearish FVG inverts (IFVG), within 30 candles, inside the **London (02:00–05:00)** or **New York (09:00–10:30)** killzone, on a closed candle |
| Signal (SELL) | The indicator's **▼ SHORT**, the mirror image |
| Skipped signals | If the stop would be wider than **3 × ATR(14)**, the indicator skips the signal (default "Skip signal if stop exceeds cap") |
| Grades traded | **A+ and B** (C is reported separately) |
| Entry | Close of the signal candle; **every signal is its own trade** (multiple entries) |
| Size | **0.01 lot = 1 ounce**: $1 of gold movement = $1 of profit |
| Take profit | **+$3** (gold moving $3 in the trade's direction) |
| Cross exit | A liquidity sweep **✗ in the trade's direction** (a buyside pool above price swept for a BUY, a sellside pool below price for a SELL), at the swept level |
| Stop loss | The indicator's stop: 2 ticks beyond the sweep low (BUY) or high (SELL) |
| Order inside a candle | Stop loss first (cautious), then whichever of the +$3 target and the cross level price reaches first |
| Holding | No time exit; a trade stays open until stop, target or cross |
| SMT partner | Silver futures `SI=F` instead of the default ES futures |
| Cost | **$0.30** spread per trade |

Indicator settings are the script defaults. Drawing-only parts (boxes, labels, dashboard,
RTH gap, volume imbalances) are not ported. The 1H and daily FVGs (used only for grading)
are built from completed hours and days of the 5-minute data.
