# RAVI v2 – NIFTY 50 Multi-Window Range Breakout (client's Final Rule Card)

ATM NIFTY option buying on 5-minute candles. Ranges and breakouts on the NIFTY 50 index;
VWAP / EMA 20 / ADX filters on the **ATM option's own 5-minute chart**. Data: **Angel One
SmartAPI** (option volume is needed for VWAP; Yahoo has no option data).

Changes from v1 (`11_ravi_v1/`), all from the client's "Final Rule Card": EMA 20 instead of 9,
no NIFTY EMA check, last window = 14:55 + 15:00 candles, max 1 CE + 1 PE per window with
reversal on an opposite signal, target ₹50 ON, trailing from +₹20 at high − ₹10, nearest weekly
expiry (also on expiry day), daily limits 6 trades / ₹10,000 loss. Added by the client after the
card: **7 EMA exit** (option premium closes below its EMA 7).

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: windows, breakouts, premium filters, entries / reversals, SL / target / trailing, daily limits, report |
| `data.py` | Angel One login (env variables), contract list (scrip master), 5m candle download and cache |
| `indicators/ema.py` + `ema.pine` | EMA (`ta.ema`): 20 (filter) and 7 (exit) |
| `indicators/vwap.py` + `vwap.pine` | VWAP, anchor Session, source hlc3 (TradingView built-in) |
| `indicators/adx.py` + `adx.pine` | ADX 14 / 14 (TradingView built-in "Average directional index") |
| `verify.py` | Independent check: indicators recomputed with pandas, every trade re-checked, exits re-simulated |
| `data/` | Downloaded candles (gitignored) |
| `results/` | `trades.csv`, `checks.csv` (every breakout close checked and why it did / did not enter), `summary.txt` |

## Run

Angel One credentials come **only from environment variables**: `ANGEL_API_KEY`,
`ANGEL_CLIENT_CODE`, `ANGEL_MPIN`, `ANGEL_TOTP_SECRET`.

```bash
python 11_ravi_v2/strategy.py --download          # download/refresh data, then backtest
python 11_ravi_v2/strategy.py                     # backtest on the cached data
python 11_ravi_v2/strategy.py --day 2026-11-26    # print one day
python 11_ravi_v2/verify.py                       # independent check of the last run
```

**Data limit:** Angel One serves candles only for option contracts that have **not expired**,
so only days whose nearest weekly expiry is still live can be tested (on 27 Nov 2026:
25–27 Nov with the 1 Dec expiry). Skipped days are listed in `summary.txt`. A longer
backtest needs a broker API that keeps expired contracts (e.g. ICICI Breeze).

## Rules as implemented

| Item | Implementation |
|---|---|
| Signal chart | NIFTY 50 index, 5-minute candles (range and breakout) |
| Trade in | NIFTY options, buy only: upside breakout → CE, downside → PE. **ATM** = NIFTY close at the signal rounded to the nearest 50. **Nearest weekly expiry** (on expiry day the expiring contract) |
| Windows | Range = high/low of: 1 **09:20**, 2 **10:00**, 3 **11:00**, 4 **12:00**, 5 **13:00**, 6 **14:00**, 7 **14:55 + 15:00 combined**. Active from the close of its (last) range candle until the next window's first range candle starts |
| Breakout | NIFTY 5m candle **closes** above the active window's high (CE) / below its low (PE) |
| Premium filters | On the ATM option being bought, at the same close: premium **above its VWAP** (windows 1–4 only), **above its EMA 20**, **ADX(14) ≥ 20**. For CE and PE alike the premium must be above VWAP / EMA 20 |
| Entry | All conditions true at a 5m close → **next 5m candle open** of the option. No entries after **15:15** |
| Per window | Max 2 trades: **at most 1 CE and 1 PE**; no same-side re-entry in the same window |
| Reversal | An opposite-side signal while in a trade closes it and opens the new side at the same next open (counts as the window's second trade). A same-side signal while already in that side is ignored |
| Holding | An open trade carries across windows until SL, target, trailing SL, 7 EMA exit, reversal or square-off. One trade at a time |
| Stop loss | **₹20** below the entry premium |
| Target | **₹50** above the entry premium |
| Trailing SL | Starts once the premium's high is **+₹20** over entry; then SL = **highest premium − ₹10**, only moves up (at +₹20 the SL is entry + ₹10). If a candle raises the SL and then **closes below it**, the price fell through it after the high: exit at the SL in that candle |
| 7 EMA exit | Option premium 5m candle **closes below its EMA 7** → exit at the **next candle open** (checked from the entry candle on) |
| Order on a candle | 7 EMA exit from the previous close (at the open), then SL, then target (candle low/high; fill at the level, or the open if it opens beyond), then the trail moves on the candle's high, then the 7 EMA check on the close |
| Square-off | **15:20** (close of the 15:15 candle) |
| Daily limits | Max **6 trades/day** (reversal entries count), max daily loss **₹10,000** (closed trades): no new trades once hit |
| Quantity | Lot 65 × lots (default 1). P&L = (exit − entry) premium × quantity, no costs |

## Settings (dashboard, defaults from the rule card)

| Setting | Default | Option |
|---|---|---|
| Max trades per day | 6 | `--max-trades` |
| Max daily loss | ₹10,000 | `--max-loss` |
| Last new-entry time | 15:15 | `--last-entry` |
| Square-off time | 15:20 | `--square-off` |
| Lots | 1 | `--lots` |
| Stop loss (premium) | ₹20 | `--sl` |
| Target (premium) | ₹50 | `--target` |
| Trail trigger / gap | ₹20 / ₹10 | `--trail-trigger`, `--trail-gap` |
| EMA period | 20 | `--ema` |
| ADX period / threshold | 14 / 20 | `--adx-len`, `--adx` |

Chart markings (dashboard): all 7 windows' ranges, breakout, CE/PE entry, SL, target and trailing SL.

## Verification

- Synthetic data (6 random runs, incl. reversals and 7 EMA exits): one trade at a time, reversal exit = next
  entry on the other side, max 1 CE + 1 PE per window, ≤ 6 trades/day, entries ≤ 15:15 at the
  next open on the ATM strike, exits ≤ 15:20; window ranges recomputed separately; every exit
  equal to a separate re-simulation of SL / target / trailing / 7 EMA / square-off.
- `verify.py` on Angel One data (25–27 Nov 2026): EMA 20, VWAP, ADX recomputed with pandas
  (max difference 0.000001); all 14 trades pass the rule re-check.
- Hand check 26 Nov, 14:00 window (high 25793.20): 14:05–14:25 closes beyond the high but the
  ATM CE was below its EMA 20 (e.g. 179.60 vs 194.11); 14:30 close 25851.30 → 25850 CE 190.65 >
  EMA 20 188.15, ADX 26.2 → entry 14:35 at 190.60, SL 170.60, target 240.60; 14:40 high 230.15
  (+39.55) → trail SL 220.15; 14:45 high 246 → target 240.60 (+50).
- Hand check 7 EMA exit, 27 Nov 12:00 window: 25700 PE signal 12:05 (160.95 > EMA 20 153.02,
  ADX 29.4) → entry 12:10 at 161.35; 12:10 close 159.25 < EMA 7 161.37 → exit 12:15 open 159.25.
