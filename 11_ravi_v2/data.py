"""Market data for this strategy: NIFTY index and NIFTY option 5-minute candles from Angel One.

Angel One SmartAPI (historical candles). Credentials are read from environment variables only,
never from files:  ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_MPIN, ANGEL_TOTP_SECRET.

Limits: Angel One serves option candles only for contracts that have not expired yet (expired
contracts are no longer in its scrip master), so a day can be tested only if the expiry the
strategy would trade on that day is still live.

Contract tokens come from Angel One's scrip master (margincalculator.angelone.in).
Downloads are cached in data/ (gitignored): nifty_5m.csv and opt_<SYMBOL>.csv.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import struct
import time as _time
import urllib.request
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

IST = "Asia/Kolkata"
BASE = "https://apiconnect.angelone.in"
NIFTY_TOKEN = "99926000"           # NSE NIFTY 50 index
SCRIP_MASTER = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
SESSION_START, SESSION_END = time(9, 15), time(15, 30)
DATA_DIR = Path(__file__).resolve().parent / "data"
_MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG",
                                       "SEP", "OCT", "NOV", "DEC"], 1)}


def _totp(secret: str) -> str:
    key = base64.b32decode(secret.upper().replace(" ", "") + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(_time.time()) // 30), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


class Angel:
    def __init__(self):
        try:
            self.key = os.environ["ANGEL_API_KEY"]
            client, mpin, secret = (os.environ[k] for k in ("ANGEL_CLIENT_CODE", "ANGEL_MPIN", "ANGEL_TOTP_SECRET"))
        except KeyError as e:
            raise SystemExit(f"Set the environment variable {e.args[0]} (Angel One login).")
        self.jwt = None
        self.jwt = self._post("/rest/auth/angelbroking/user/v1/loginByPassword",
                              {"clientcode": client, "password": mpin, "totp": _totp(secret)})["data"]["jwtToken"]

    def _post(self, path: str, body: dict, tries: int = 6) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json", "X-UserType": "USER",
             "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
             "X-MACAddress": "00:00:00:00:00:00", "X-PrivateKey": self.key}
        if self.jwt:
            h["Authorization"] = f"Bearer {self.jwt}"
        last_err = None
        for k in range(tries):
            try:
                req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=h)
                with urllib.request.urlopen(req, timeout=30) as r:
                    out = json.loads(r.read().decode())
            except Exception as e:                              # rate limit / network: back off
                last_err = e
                _time.sleep(2.0 * (k + 1))
                continue
            if out.get("status"):
                return out
            if out.get("errorcode") in ("AB1004", "AB2001") and k < tries - 1:   # too many requests
                _time.sleep(1.5 * (k + 1))
                continue
            raise SystemExit(f"Angel One API error {path}: {out.get('message')} ({out.get('errorcode')})")
        raise SystemExit(f"Angel One API: no answer for {path} ({last_err})")

    def nifty_options(self) -> pd.DataFrame:
        """All live NIFTY option contracts (Angel One scrip master): symbol, token, expiry, strike, type."""
        with urllib.request.urlopen(SCRIP_MASTER, timeout=120) as r:
            rows = json.loads(r.read().decode())
        out = []
        for r in rows:
            if r.get("exch_seg") != "NFO" or r.get("name") != "NIFTY" or r.get("instrumenttype") != "OPTIDX":
                continue
            m = re.fullmatch(r"NIFTY(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)", r["symbol"])
            if m:
                dd, mon, yy, k, typ = m.groups()
                out.append(dict(symbol=r["symbol"], token=r["token"],
                                expiry=date(2000 + int(yy), _MONTHS[mon], int(dd)), strike=int(k), type=typ))
        return pd.DataFrame(out)

    def candles(self, exchange: str, token: str, start: datetime, end: datetime) -> pd.DataFrame:
        out = self._post("/rest/secure/angelbroking/historical/v1/getCandleData",
                         {"exchange": exchange, "symboltoken": token, "interval": "FIVE_MINUTE",
                          "fromdate": start.strftime("%Y-%m-%d %H:%M"), "todate": end.strftime("%Y-%m-%d %H:%M")})
        _time.sleep(0.6)                                          # stay under the rate limit
        df = pd.DataFrame(out.get("data") or [], columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
        df["Datetime"] = pd.to_datetime(df["Datetime"])
        return df.set_index("Datetime")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """IST index, sorted, no duplicates, 09:15-15:30 candles only."""
    df = df.copy()
    idx = pd.DatetimeIndex(df.index)
    df.index = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    return df[(t >= SESSION_START) & (t < SESSION_END)]


def load_cached(name: str) -> pd.DataFrame | None:
    p = DATA_DIR / f"{name}.csv"
    if not p.exists():
        return None
    return clean(pd.read_csv(p, index_col=0, parse_dates=True))


def save_cached(name: str, df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_DIR / f"{name}.csv")


def download(days_expiries: list[tuple[date, date]], nifty_from: date, nifty_to: date, band: int = 250) -> None:
    """Download NIFTY 5m (nifty_from..nifty_to) and, for every (day, expiry), the CE and PE of
    every 50-point strike within `band` points of that day's NIFTY range, 5m, from 12 days
    before the day (indicator warm-up) to the day's close. Cached in data/."""
    a = Angel()
    start = datetime.combine(nifty_from, SESSION_START)
    end = datetime.combine(nifty_to, SESSION_END)
    nifty = a.candles("NSE", NIFTY_TOKEN, start, end)
    save_cached("nifty_5m", nifty[["Open", "High", "Low", "Close"]])
    nifty = clean(nifty)
    live = a.nifty_options()
    for day, exp in days_expiries:
        d = nifty[nifty.index.date == day]
        if d.empty:
            continue
        lo = int((d.Low.min() - band) // 50 * 50)
        hi = int(-(-(d.High.max() + band) // 50) * 50)
        need = live[(live.expiry == exp) & live.strike.between(lo, hi)]
        f = datetime.combine(day, SESSION_START) - pd.Timedelta(days=12)
        t = datetime.combine(day, SESSION_END)
        for _, c in need.iterrows():
            old = load_cached(f"opt_{c.symbol}")
            if old is not None and len(old) and old.index.min().date() <= f.date() and old.index.max().date() >= day:
                continue
            try:
                df = a.candles("NFO", c.token, f, t)
            except SystemExit as e:
                print(f"    {c.symbol}: skipped ({e})")
                continue
            if old is not None:
                df = pd.concat([clean(old), clean(df)])
            save_cached(f"opt_{c.symbol}", clean(df))
        print(f"  {day}: expiry {exp}, strikes {lo}-{hi} ({len(need)} contracts)")
    pd.DataFrame(live).to_csv(DATA_DIR / "contracts.csv", index=False)
