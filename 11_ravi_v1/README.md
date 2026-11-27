# RAVI v1 – NIFTY ORB (hourly range breakout, ATM option buying)

5-minute NIFTY range breakout with confirmations on the **ATM option's own chart** (VWAP,
EMA, ADX). Data: **Angel One SmartAPI** 5-minute candles for the NIFTY index and NIFTY
options (option volume is needed for VWAP; Yahoo has no option data).

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: ranges, breakouts, confirmations, entries, SL / trailing / 7 EMA exit, limits, report |
| `data.py` | Angel One login (env variables), contract list (scrip master), 5m candle download and cache |
| `indicators/ema.py` + `ema.pine` | EMA (`ta.ema`): NIFTY 9, premium 9 / 20, exit 7 |
| `indicators/vwap.py` + `vwap.pine` | VWAP, anchor Session, source hlc3 (TradingView built-in) |
| `indicators/adx.py` + `adx.pine` | ADX, smoothing 14, DI length 14 (TradingView built-in) |
| `verify.py` | Independent check: indicators recomputed with pandas, every trade re-checked and its exit re-simulated |
| `data/` | Downloaded candles (gitignored) |
| `results/` | `trades.csv`, `checks.csv` (every breakout close checked and why it did / did not enter), `summary.txt` |

The `.pine` files are TradingView's official sources (`STD;EMA`, `STD;VWAP`,
`STD;Average Directional Index`); the Python ports follow them.

## Run

Angel One credentials come **only from environment variables** (never put them in a file):
`ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_MPIN`, `ANGEL_TOTP_SECRET`.

```bash
python 11_ravi_v1/strategy.py --download          # download/refresh data, then backtest
python 11_ravi_v1/strategy.py                     # backtest on the cached data
python 11_ravi_v1/strategy.py --day 2026-11-26    # print one day
python 11_ravi_v1/verify.py                       # independent check of the last run
```

**Data limit:** Angel One serves candles only for option contracts that have **not expired**.
A day can be tested only when the expiry it trades is still live (e.g. on 27 Nov 2026:
25–27 Nov → 1 Dec contracts; 24 Nov and earlier traded the expired 24 Nov contracts). Earlier days are skipped
and listed in `summary.txt`. A broker API that keeps expired contracts (ICICI Breeze) is
needed for a longer backtest.

## Rules as implemented

| Item | Implementation |
|---|---|
| Timeframe | 5-minute candles. NIFTY index for ranges/breakouts; ATM NIFTY option for confirmations and P&L |
| Ranges | High/low of the 5m candles starting **09:20, 10:00, 11:00, 12:00, 13:00, 14:00, 15:00**. A range is active from its candle's close until the next range candle starts (then it ends) |
| Breakout | NIFTY 5m candle **closes** above the range high → CE; below the range low → PE. A touch does not count |
| Option | **ATM = NIFTY close rounded to the nearest 50**, re-taken on every close checked, of the chosen expiry |
| Morning (09:20–12:00 ranges) | Option close **above its VWAP** + NIFTY close **above (CE) / below (PE) its 9 EMA** + option close **above its 9 EMA** + option **ADX ≥ 20**. For a PE the PE premium must be above its VWAP / 9 EMA |
| Afternoon (13:00–15:00 ranges) | **No VWAP.** Option close above its **9 EMA** (setting: 20) + NIFTY above/below its 9 EMA + option ADX ≥ 20 |
| Waiting | Checked on every 5m close while NIFTY is **still closed beyond** the range. If NIFTY closes back inside, it waits for a new break |
| Entry | **Next 5m candle open** of the option. Entries until the **15:15** candle open |
| Stop loss | **₹20** below the entry premium |
| Trailing SL | Starts at once: every **₹10** the premium's high gains over entry moves the SL up **₹10** (+10 → SL −10, +20 → cost, +30 → +10, …) |
| Target | **₹40, OFF by default** (`--target`) |
| 7 EMA exit | Option 5m candle **closes below its 7 EMA** → exit at the next candle open |
| Square-off | **15:20** (close of the 15:15 candle) |
| Order on a candle | SL / trailing SL first (fill at the level, or the open if it opens beyond), then target, then the trail moves on the candle's high, then the 7 EMA check on the close |
| Trades | **One at a time**; max **2 per range** (`--per-range 1`); a trade still open when the next range starts runs to its own exit; new entries only after it closes |
| Second trade | Same side only after a **fresh break**: NIFTY must close back out of that side (inside, or beyond the other side) and then break again; the other side can trade at once |
| Daily locks | Max trades / loss lock ₹ / profit lock ₹ (`--max-trades`, `--loss-lock`, `--profit-lock`), **OFF by default**. Checked when a trade closes: no new entries that day |
| Gap-day switch | `--no-ema` drops all EMA confirmations (VWAP and ADX stay). OFF in the backtest; manual on the dashboard |
| Expiry | `current` (default): this week's NIFTY expiry; **on expiry day the next week's**. `next`: the one after |
| Quantity | Lot 65 × `--lots` (default 1). P&L = (exit − entry) premium × quantity, no costs |

## Dashboard settings (from the client's spec)

ADX threshold (20), afternoon premium EMA (9/20), target ON/OFF (OFF), trades per range (1/2),
EMA disable switch (gap days), expiry (current/next), lots, daily trade / loss / profit locks.
Chart markings (dashboard): all 7 ranges, breakout, CE/PE entry, SL, target and trailing SL.

## Verification

- Synthetic data: no overlapping trades, ≤ 2 per range, entries only on the next open at the
  ATM strike of the signal close and until 15:15, exits by 15:20; every exit equal to a
  separate re-simulation of SL / trailing / 7 EMA / square-off.
- `verify.py` on Angel One data (25–27 Nov 2026): EMA, VWAP and ADX recomputed with pandas,
  max difference 0.000001; all 21 trades pass the rule re-check (conditions at the signal
  close, entry price, exit, fresh break, no overlap).
- Hand check 26 Nov, 14:00 range (high 25793.20): 14:05 close 25830.25 > high and > 9 EMA
  25820.92, ATM 25850 CE close 179.60 > 9 EMA 176.49, ADX 31.2 → entry 14:10 at 179.15, SL
  159.15 hit (low 156.10). 14:10 close back inside, 14:15 close 25824.85 breaks again → ATM 25800
  CE, entry 14:20 at 198.80, SL 178.80 → 188.80 → 198.80 → 208.80 → 238.80 → 248.80 as the
  highs rise to 278, exit 14:50 at 248.80 (+50).
