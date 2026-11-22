# Strategy backtesting workflow (read this first)

You build and backtest clients' trading strategies (NSE stocks/indices, forex, gold) in this
repo. The user sends a strategy in plain words (often Hinglish), sometimes with TradingView
Pine source code. Your job: turn it into a **correct, verified backtest** that matches how the
client reads their chart, then answer questions about the trades.

## 1. Before writing any code

1. **Read the whole spec and list every rule that can be read in more than one way.** Typical
   ones: entry candle (signal close vs next open), what "cross"/"break" means (wick or close,
   strict or touch), stop-loss and target basis, timeframe, session start/end, last entry
   time, square-off time, one position or several, reversal or not, re-entry after exit,
   quantity/lot size, which symbol, test period.
2. **Indicators:** built-ins (SMA, EMA, MACD, RSI, ATR...) need no source; confirm settings.
   For any **community / third-party indicator, ask for the exact Pine source before
   implementing** (TradingView: hover the indicator name → `{ }` → copy all). Never port a
   community indicator from memory; that caused wrong results before.
3. **Ask doubt questions as MCQs in plain text** (not pop-up tools):
   - numbered questions, options **A / B / C**, mark the one the code uses now as *(current)*
     or the sensible one as *(recommended)*;
   - only ask what changes trades; keep each option one or two lines;
   - tell the user how to reply: e.g. **"1A 2B 3A"**;
   - list your assumptions for the rest so they can correct them.
4. If the user answers only some questions, use the recommended option for the rest and say so.

## 2. Building

- **One folder per person, fully self-contained** (nothing shared between strategies, never
  import from another folder):
  ```
  <name>/
    README.md        rules as implemented (table), data used, how to run
    strategy.py      backtest + report (runs from repo root: python <name>/strategy.py)
    data.py          its own data loader
    indicators/      one Python file per indicator + the original .pine source if given
    results/         output (gitignored)
  ```
  Add the strategy to the root `README.md` table and folder tree.
- Port Pine faithfully: same order of operations per bar, `ta.ema` SMA-seeded, `ta.atr` = RMA,
  `ta.pivothigh/low` confirm `right` bars later, `na` comparisons are false, `var` state.
- After the user confirms a choice, **implement that only. Do not keep alternative options
  / flags around and do not offer "another option"** unless asked.
- Default execution: signal on candle close, fill at next candle open; if one candle touches
  both SL and target, count the **SL first**. State this in the README.

## 3. Verify before reporting (always)

- Test on synthetic data first (runs, invariants: entries only in allowed times, exits by
  square-off, P&L math, no overlapping positions when one-at-a-time).
- **Independent check**: recompute signals/indicators with a separate simple method
  (brute force, pandas) and compare; hand-check at least one trade candle by candle.
- When refactoring, save outputs first and confirm trades are **identical** afterwards.
- Look for suspicious numbers (e.g. "70 targets but 54 wins") and find the cause.
- Report honestly: what was verified, what is approximate, what data was used.

## 4. Data (yfinance, unofficial)

| Need | Symbol / limit |
|---|---|
| NSE stock | `RELIANCE.NS` etc. 1m ≈ 30 days, 2m/5m/15m ≈ 60 days |
| NIFTY 50 | `^NSEI` (**no volume** → no RVOL/volume rules on indices) |
| India VIX | `^INDIAVIX` |
| Gold | `GC=F` COMEX futures (**no spot XAUUSD on Yahoo**); silver `SI=F` |
| 3-minute | not on Yahoo → build from 1m (bins from 09:15) |
| Options | **not on Yahoo**. NSE F&O bhavcopy = daily close only (`nsearchives.nseindia.com`). Intraday option data needs a broker API (Breeze keeps expired contracts) |
| TradingView candles / closed-source script outputs | TradingView-API with the user's cookies in `TV_SESSION` / `TV_SIGNATURE` (see `alia/tv_download`). Password login is blocked from servers; send a browser user agent. Free plan: NSE delayed, ~5,000 candles. TradingView NSE 3m (`NSE:NIFTY`, `NSE:RELIANCE`) has **no candles after 15:15** (Yahoo has 15:15–15:29: drop them) |

- NSE session 09:15–15:30 IST (nothing executes after 15:30). RELIANCE tick ₹0.10;
  NIFTY strikes step 50, lot 65, weekly expiry Tuesday (holiday → previous trading day).
- Futures/forex sessions use New York time when the script says so.
- Yahoo prices differ slightly from TradingView/broker feeds; a signal decided by a few paise
  can differ. Ask the user for the chart value before calling it a bug.

## 5. Known chart-reading pitfalls (explain these when trades "don't match")

- **Labels drawn back in time:** LuxAlgo pivots (50 bars late), Liquidity Swings zones,
  Reversal Entry Zones labels appear on the chart later but sit on the pivot candle. Ask
  whether the client reads the **label position** or the **confirmation time**, then follow
  their answer.
- **LuxAlgo Liquidity Swings, Count filter 0**: a zone box is drawn only after price trades
  back into it; one faint box always sits on the latest swing and moves.
- **Kyle Algo colours candles by its Supertrend** (`barcolor`): a red candle can be an up
  candle. Check O/C in the data window.
- Free TradingView: no intraday Replay; check by scrolling back (non-repainting indicators).

## 6. Answering the user

- Trade lists in **short text tables in a code block**: `Date  Side  Entry  Exit  Reason`.
  **No prices or P&L unless asked.**
- Show results **only for the rules the user confirmed**. No side-by-side "what if" versions
  (e.g. hindsight vs live) unless the user asks; mention a caveat once at most.
- Be concise; Hinglish replies are fine when the user writes Hinglish.
- When asked "why this trade", show the few candles/values that decided it.
- "Last N days" = trading sessions in that calendar window; say which dates.

## 7. Safety and housekeeping

- Never write API keys, MPIN, TOTP secrets or passwords into files or commits; read them from
  environment variables. If the user pastes secrets in chat, warn them to rotate them.
- Network hosts must be allowed in the cloud environment (Yahoo: `query1/query2.finance.yahoo.com`,
  `fc.yahoo.com`, `guce.yahoo.com`). Ask once; if declined, say what is blocked.
- Commit with clear messages and push to the working branch after each change.

## 8. Strategies so far (decisions already confirmed)

- **neeraj/** Kyle Algo EMA ribbon + Liquidity Swings, 5m. Fresh close above/below the full
  ribbon → CALL/PUT next open; every signal its own trade; exit at the RED/GREEN zone's
  swing candle (label position), 1% SL, 15:15 square-off. Open question: why the client
  expects some entries the data doesn't give (ribbon close margins, zone touches).
- **laxit/** SMA20 High/Low + MACD, **2m**. Setup candle: green/red, >50% body beyond SMA,
  MACD cross on that candle; entry next candle break only; SL follows the SMA line; at 1:1
  book 50% and move SL to cost (no trailing); entries 09:45–14:20, square-off 15:15.
- **rakesh/** 7 EMAs, 5m. BUY when the 60 EMA crosses **above** all others (SELL below);
  next open; SL 1 tick beyond the crossover candle; 50% at 1:1 → cost, rest at 1:2.
- **toufik/** EMA4/SMA10, 3m (from 1m). Crossover → reverse; 1% SL; entries until 15:00.
- **ashishkumarverma/** ORB on 15m only: opening candle high/low (wick), alert = first close
  beyond it, entry on break of the alert candle wick (at the level) until 13:30, SL alert
  candle capped 1%, exit on 15m close across 9 EMA, RVOL(20, same time slot, 20 days) ≥ 1.5
  on opening and alert candles, gap > 2% no trade, square-off 15:00.
- **amitrajdev/** SMA120 + LuxAlgo pivots + Reversal Entry Zones + Smoothed HA, 5m. All 4
  newly align → entry next open; exit when 2+ conditions are against **at the same close**;
  LuxAlgo/RevZones read at **label position**; no SL; entries to 15:00, square-off 15:15.
- **praful/** ICT Session Scalper Toolkit on gold (`GC=F`), 5m, New York time. A+/B signals,
  every signal a trade, 0.01 lot, +$3 target, exit on a ✗ sweep in the trade's direction,
  indicator SL (sweep extreme ± 2 ticks, capped 3×ATR14), $0.30 spread, SMT vs silver.
- **alia/** (client Alia) closed-source invite-only TradingView strategy "Od trading software no wm",
  decoded from its outputs. Its trades: ATR trailing stop on EMA 4 of close (1.7 × ATR 7);
  EMA crossing it → next open, reverse on the opposite signal, 10/20-point SL/TP from the next
  candle, held overnight (replay 616/620 TradingView trades on NIFTY, RELIANCE, SBIN, HDFCBANK;
  misses only around TradingView margin calls on stocks). Its DEMA 20 × SMA 40 arrows are
  display only. **Backtest (confirmed):** the script's entries + stop = closer of 10 pts / 1%;
  at +20 pts no booking: stop to breakeven, then trail 1% behind the best price; no session,
  held overnight like the script. Indian markets only (no BTC).
- **suneet/** Williams Fractal 7 (TradingView built-in, source in `indicators/`), NIFTY 3m.
  Red arrow → CE, green → PE; signal = **arrow candle (label position, hindsight)**, entry next
  open; SL = arrow candle wick; opposite arrow → exit + reverse; same-side arrow ignored; after
  SL any arrow re-enters; entries before 15:00, square-off 15:15. P&L in index points; each trade
  lists CE ATM−50 / PE ATM+100, nearest Tuesday expiry (next week on expiry day). Port = TV
  output 444/444 arrows.
