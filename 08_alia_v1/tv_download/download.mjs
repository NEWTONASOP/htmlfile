#!/usr/bin/env node
/**
 * Downloads candles, plots and Strategy-Tester trades of the invite-only TradingView script
 * "Od trading software no wm" (OD SOFTWARE) with your own TradingView account, using the
 * unofficial TradingView-API library (https://github.com/Mathieu2301/TradingView-API).
 * The account must have been given access to the script.
 *
 * Cookies come ONLY from environment variables. Never write them into a file or commit:
 *   TV_SESSION    value of the `sessionid` cookie of www.tradingview.com
 *   TV_SIGNATURE  value of the `sessionid_sign` cookie
 *
 * Usage (from the repository root):
 *   npm --prefix 08_alia_v1/tv_download install          # once
 *   node 08_alia_v1/tv_download/download.mjs [SYMBOL] [TIMEFRAME] [BARS]
 *   node 08_alia_v1/tv_download/download.mjs NSE:NIFTY 3 6000
 *
 * Writes (gitignored):
 *   08_alia_v1/data/<SYMBOL>_<TF>.csv            candles (IST) + the script's MA lines and arrows
 *   08_alia_v1/data/<SYMBOL>_<TF>_tv_trades.csv  the script's own Strategy-Tester trade list
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  createProxy, getUser, getIndicator, getIndicatorData, TradingViewClient,
} from '@mathieuc/tradingview';

const SCRIPT_ID = 'PUB;bd646e96ec1548949f18d637a39a7d20'; // tradingview.com/v/SQYvrxuA
// Screener table symbols are pointed here: the table asks for 30 NSE stocks, which a
// free-plan account is not authorised for (study error "symbol_not_auth"). The table is
// display-only and does not affect the MA lines or arrows.
const SCREENER_DUMMY = 'OANDA:XAUUSD';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
  + '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const NA = 1e100; // TradingView's na in plot values
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(HERE, '..', 'data');

const [symbol = 'NSE:NIFTY', timeframe = '3', bars = '6000'] = process.argv.slice(2);
const credentials = { session: process.env.TV_SESSION, signature: process.env.TV_SIGNATURE };
if (!credentials.session || !credentials.signature) {
  console.error('Set TV_SESSION and TV_SIGNATURE (tradingview.com cookies sessionid / sessionid_sign).');
  process.exit(1);
}

// Optional HTTPS proxy (cloud sandboxes); a local PC normally has none.
const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy;
let proxy;
if (proxyUrl) {
  const caFile = process.env.NODE_EXTRA_CA_CERTS;
  const ca = caFile && fs.existsSync(caFile) ? fs.readFileSync(caFile, 'utf8') : undefined;
  proxy = createProxy(proxyUrl, ca ? { tls: { ca } } : undefined);
}
const baseFetch = proxy ? proxy.fetch : globalThis.fetch;
// TradingView's CDN answers 403 to the account page without a browser user agent.
const uaFetch = (url, opts = {}) => {
  const headers = new Headers(opts.headers || {});
  headers.set('user-agent', UA);
  return baseFetch(url, { ...opts, headers });
};

const istIso = (unixSec) => new Date((unixSec + 19800) * 1000).toISOString()
  .replace(/\.\d{3}Z$/, '+05:30');
const num = (v) => (v === undefined || v === null || v >= NA ? '' : v);

function inputKey(ind, name) {
  const key = Object.keys(ind.inputs).find((k) => ind.inputs[k].name === name);
  if (!key) throw new Error(`input "${name}" not found: the script may have changed`);
  return key;
}

const user = await getUser(credentials, { fetch: uaFetch, headers: { 'user-agent': UA } });
console.log(`logged in as ${user.username}`);
const ind = await getIndicator(SCRIPT_ID, { credentials, fetch: uaFetch });
const inputs = { [inputKey(ind, 'Screener')]: false, [inputKey(ind, 'Plot fastMA')]: true };
for (const [k, v] of Object.entries(ind.inputs)) if (v.type === 'symbol') inputs[k] = SCREENER_DUMMY;
ind.setInputs(inputs);

const client = new TradingViewClient({
  authToken: user.authToken, ...(proxy ? { transport: proxy.transport } : {}),
});
let data;
try {
  data = await getIndicatorData({
    symbol, timeframe, count: Number(bars), indicator: ind, client, timeoutMs: 180000,
  });
} finally {
  await client.close();
}

const plots = new Map(data.values.map((v) => [v.$time, v]));
const rows = ['Datetime,Open,High,Low,Close,Volume,TV_FastMA,TV_SlowMA,TV_BuyArrow,TV_SellArrow'];
let buys = 0;
let sells = 0;
for (const c of data.candles) {
  const p = plots.get(c.time) || {};
  // arrow plots: price of the arrow on its candle, na elsewhere
  const buy = num(p.Long_Signal) === '' ? 0 : 1;
  const sell = num(p.Short_Signal) === '' ? 0 : 1;
  buys += buy;
  sells += sell;
  rows.push([istIso(c.time), c.open, c.high, c.low, c.close, c.volume ?? '',
    num(p.Fast_MA), num(p.Trend_MA_line), buy, sell].join(','));
}

const trades = [...(data.strategyReport?.trades || [])]
  .sort((a, b) => a.entry.time - b.entry.time)
  .map((t) => [istIso(t.entry.time / 1000), t.entry.type.toUpperCase(), t.entry.value,
    istIso(t.exit.time / 1000), t.exit.value, t.exit.name, t.quantity, t.profit?.v ?? ''].join(','));

fs.mkdirSync(OUT_DIR, { recursive: true });
const base = path.join(OUT_DIR, `${symbol.replace(/[:!]/g, '_')}_${timeframe}`);
fs.writeFileSync(`${base}.csv`, `${rows.join('\n')}\n`);
fs.writeFileSync(`${base}_tv_trades.csv`,
  `entry_time,side,entry,exit_time,exit,reason,qty,profit\n${trades.join('\n')}\n`);

const first = data.candles[0]?.time;
const last = data.candles.at(-1)?.time;
console.log(`${symbol} ${timeframe}m: ${data.candles.length} candles ${istIso(first)} -> ${istIso(last)}`);
console.log(`arrows: ${buys} BUY, ${sells} SELL | Strategy-Tester trades: ${trades.length}`);
console.log(`wrote ${path.relative(process.cwd(), `${base}.csv`)} and ${path.relative(process.cwd(), `${base}_tv_trades.csv`)}`);
