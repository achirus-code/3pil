"""Tageskurse von Yahoo Finance – nur als Rückfall, wenn Trade Republic für eine ISIN keine (ausreichenden) liefert."""

from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
CHART = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146 Safari/537.36",
           "Accept": "application/json"}
TIMEOUT = aiohttp.ClientTimeout(total=20)
# Euro-Handelsplätze in der Reihenfolge, in der sie bevorzugt werden
EUR_SUFFIXES = (".DE", ".F", ".MU", ".SG", ".BE", ".DU", ".HM", ".AS", ".PA", ".MI")


async def yahoo_candles(session: aiohttp.ClientSession, isin: str) -> list[dict] | None:
    """[{time (ms), close}] in Euro, bis zu 10 Jahre täglich – oder None."""
    try:
        async with session.get(SEARCH, params={"q": isin, "quotesCount": 10, "newsCount": 0},
                               headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status >= 300:
                return None
            quotes = (await resp.json(content_type=None)).get("quotes") or []
        symbols = [q["symbol"] for q in quotes if q.get("symbol")]
        symbols.sort(key=lambda s: next((i for i, suf in enumerate(EUR_SUFFIXES) if s.endswith(suf)), 99))
        for symbol in symbols[:4]:
            async with session.get(CHART.format(symbol=symbol), params={"range": "10y", "interval": "1d"},
                                   headers=HEADERS, timeout=TIMEOUT) as resp:
                if resp.status >= 300:
                    continue
                result = ((await resp.json(content_type=None)).get("chart") or {}).get("result") or []
            if not result or (result[0].get("meta") or {}).get("currency") != "EUR":
                continue
            times = result[0].get("timestamp") or []
            closes = (((result[0].get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
            out = [{"time": int(t) * 1000, "close": float(c)} for t, c in zip(times, closes) if c is not None]
            if out:
                _LOGGER.info("Yahoo-Kurse für %s über %s (%s Tage)", isin, symbol, len(out))
                return out
    except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError) as err:
        _LOGGER.info("Yahoo-Kurse für %s nicht geladen: %s", isin, err)
    return None
