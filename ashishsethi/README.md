# ASHISH SETHI – NIFTY Option Selling

Backtest of a NIFTY option-selling strategy using **NIFTY spot only**: no historical option
data is used. Each option's premium is estimated from NIFTY spot with Black-Scholes, using
India VIX as the volatility. Data: NIFTY 50 and India VIX 5-minute candles from Yahoo
(about the last 60 days).

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: reference price, entries, daily/open-lot limits, per-leg SL and target, expiry square-off, report |
| `indicators/black_scholes.py` | Option premium from NIFTY spot, strike, time to expiry and India VIX |
| `indicators/expiry.py` | Weekly expiry (Tuesday, previous trading day if a holiday) and strike selection |
| `data.py` | Data loader: Yahoo 5-minute candles, IST session |
| `results/` | Output of the last run: `legs.csv` (every leg), `summary.txt` |

## Run

```bash
pip install -r requirements.txt
python ashishsethi/strategy.py            # all available days (~60)
python ashishsethi/strategy.py --lot 65   # lot size for Rs P&L
```

## Rules as implemented

| Item | Implementation |
|---|---|
| Reference Price (RP) | NIFTY **09:15 open** at the start of each day (pending the client's final answer). Resets to the spot at every successful entry |
| CE entry | NIFTY **70 points above RP** → sell 1 CE, strike = nearest multiple of 50 to spot **+ 200** |
| PE entry | NIFTY **70 points below RP** → sell 1 PE, strike = nearest multiple of 50 to spot **− 200** |
| Fill | Market order at the moment NIFTY crosses the level (the level itself), premium from Black-Scholes, on a 0.05 tick |
| Expiry | Next weekly expiry: **Tuesday** (previous trading day if Tuesday is a holiday). On expiry day, today's expiry |
| Limits | Max **5 new lots per day**, max **40 open lots** in total. When capacity frees up, entries resume within the daily limit. A blocked entry does not reset RP |
| Stop loss | Each leg: premium **+30%** above its selling price |
| Target | Each leg: premium **−90%** below its selling price |
| Square-off | Expiry day only, all open legs at the **close** (NSE closes 15:30; the spec's 15:33 is after the close). At expiry the premium is the intrinsic value |
| Overnight | Legs are held across days until SL, target or expiry |
| Inside a candle | The 5-minute candle is walked open → low → high → close (rising candle) or open → high → low → close (falling) in 2-point steps; exits are checked before new entries at every step |
| Safety items | No duplicate entries is built in (one entry per trigger, RP resets). Rejected / partial orders and exit verification apply to live order handling, not to a backtest |

## Premium model (approximation)

`premium = Black-Scholes(spot, strike, time to 15:30 on expiry day, India VIX / 100, r = 6.5%)`

Real premiums also depend on each strike's own implied volatility (out-of-the-money options
usually trade above this estimate, especially close to expiry), bid-ask spreads and demand.
Results are therefore an estimate of how the rules behave, not exact option P&L.
