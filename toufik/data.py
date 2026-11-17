"""Market data for this strategy: 1-minute yfinance data built into N-minute candles (IST).

yfinance has no 3-minute interval, so 1-minute candles are downloaded and grouped into
3-minute candles starting at 09:15 (09:15, 09:18, ...), the same grid TradingView uses for NSE.
yfinance keeps 1-minute data for about the last 30 days, at most 7 days per request.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

IST = "Asia/Kolkata"


def fetch_1m(symbol: str, days: int = 7) -> pd.DataFrame:
    """Last `days` calendar days of 1-minute OHLC, fetched in 7-day chunks."""
    import yfinance as yf

    end = pd.Timestamp.now(tz=IST).normalize() + pd.Timedelta(days=1)
    start_all = end - pd.Timedelta(days=min(days, 29) + 1)
    parts = []
    s = start_all
    while s < end:
        e = min(s + pd.Timedelta(days=7), end)
        df = yf.download(symbol, start=s.strftime("%Y-%m-%d"), end=e.strftime("%Y-%m-%d"),
                         interval="1m", progress=False, auto_adjust=False, multi_level_index=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            parts.append(df)
        s = e
    if not parts:
        raise SystemExit(f"yfinance returned no 1-minute data for {symbol}. "
                         "Check network access to query1/query2.finance.yahoo.com.")
    return pd.concat(parts)


# ---------------------------------------------------------------- Angel One SmartAPI
# Credentials are read from environment variables only - never put them in this repo:
#   ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_MPIN, ANGEL_TOTP_SECRET
ANGEL_BASE = "https://apiconnect.angelone.in"
ANGEL_TOKENS = {"RELIANCE": "2885"}  # NSE equity symbol tokens (RELIANCE-EQ)
ANGEL_INTERVALS = {1: "ONE_MINUTE", 3: "THREE_MINUTE", 5: "FIVE_MINUTE", 10: "TEN_MINUTE",
                   15: "FIFTEEN_MINUTE", 30: "THIRTY_MINUTE", 60: "ONE_HOUR"}


def _totp(secret_b32: str, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP (same code the authenticator app shows)."""
    import base64
    import hashlib
    import hmac
    import struct
    import time as _time

    key = base64.b32decode(secret_b32.upper().replace(" ", "") + "=" * (-len(secret_b32) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(_time.time()) // step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def _angel_post(path: str, body: dict, api_key: str, jwt: str | None = None) -> dict:
    import json
    import urllib.request

    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "X-UserType": "USER", "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1",
               "X-ClientPublicIP": "127.0.0.1", "X-MACAddress": "00:00:00:00:00:00",
               "X-PrivateKey": api_key}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    req = urllib.request.Request(ANGEL_BASE + path, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    if not out.get("status"):
        raise SystemExit(f"Angel One API error on {path}: {out.get('message')} ({out.get('errorcode')})")
    return out


def fetch_angel(symbol: str, minutes: int, days: int) -> pd.DataFrame:
    """Candles straight from Angel One SmartAPI (native 3-minute candles, IST)."""
    import os

    try:
        api_key = os.environ["ANGEL_API_KEY"]
        client = os.environ["ANGEL_CLIENT_CODE"]
        mpin = os.environ["ANGEL_MPIN"]
        secret = os.environ["ANGEL_TOTP_SECRET"]
    except KeyError as e:
        raise SystemExit(f"Set the environment variable {e.args[0]} for --source angel.")
    name = symbol.split(".")[0].upper()
    token = ANGEL_TOKENS.get(name)
    if token is None:
        raise SystemExit(f"No Angel One symbol token known for {name}; add it to ANGEL_TOKENS.")

    login = _angel_post("/rest/auth/angelbroking/user/v1/loginByPassword",
                        {"clientcode": client, "password": mpin, "totp": _totp(secret)}, api_key)
    jwt = login["data"]["jwtToken"]
    end = pd.Timestamp.now(tz=IST)
    start = (end - pd.Timedelta(days=days)).normalize() + pd.Timedelta(hours=9, minutes=15)
    out = _angel_post("/rest/secure/angelbroking/historical/v1/getCandleData",
                      {"exchange": "NSE", "symboltoken": token, "interval": ANGEL_INTERVALS[minutes],
                       "fromdate": start.strftime("%Y-%m-%d %H:%M"), "todate": end.strftime("%Y-%m-%d %H:%M")},
                      api_key, jwt)
    rows = out.get("data") or []
    if not rows:
        raise SystemExit("Angel One returned no candles.")
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    return df.set_index("Datetime")


def load_csv(path: str) -> pd.DataFrame:
    """CSV with a Datetime (or Date/Time/Timestamp) column plus Open, High, Low, Close."""
    df = pd.read_csv(path)
    tcol = next(c for c in df.columns if c.lower() in ("datetime", "date", "time", "timestamp"))
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep OHLC, convert to IST, drop duplicates and candles outside 09:15-15:30."""
    df = df[["Open", "High", "Low", "Close"]].dropna().copy()
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    df.index = idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    return df[(t >= time(9, 15)) & (t < time(15, 30))]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Group candles into `minutes`-minute candles labelled by their start time.

    Bins start at midnight IST, so for 3 minutes they fall on 09:15, 09:18, ... (555 % 3 == 0).
    """
    out = df.resample(f"{minutes}min", origin="start_day", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    t = out.index.time
    return out[(t >= time(9, 15)) & (t < time(15, 30))]
