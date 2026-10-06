"""Laden der Wirtschaftsdaten (ohne Login).

Euribor 3M und EUR/USD von der EZB, US-Arbeitslosenquote vom BLS, US-Erstanträge (DOL,
nicht saisonbereinigt; über FRED „ICNSA“, da der DOL-Export ar539 oft nicht erreichbar ist)
und die US-Zinskurve aus den Daily Treasury Rates.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date

import aiohttp

_LOGGER = logging.getLogger(__name__)

ECB = "https://data-api.ecb.europa.eu/service/data/{flow}?format=csvdata&detail=dataonly&lastNObservations={n}"
EURIBOR_FLOW = "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA"
EURUSD_FLOW = "EXR/M.USD.EUR.SP00.E"
ECB_DFR_FLOW = "FM/D.U2.EUR.4F.KR.DFR.LEV"  # Einlagensatz der EZB (täglich)
BLS_V2 = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_V1 = "https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000"
FRED_CLAIMS = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICNSA&cosd={start}"
TREASURY = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
    "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)

TIMEOUT = aiohttp.ClientTimeout(total=45)
# FRED weist Browser- und „HomeAssistant/…“-Kennungen ab, die schlichte aiohttp-Kennung nicht
HEADERS = {"User-Agent": f"Python/3 aiohttp/{aiohttp.__version__}"}


async def _text(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, timeout=TIMEOUT, headers=HEADERS) as resp:
        resp.raise_for_status()
        return await resp.text()


async def _ecb(session: aiohttp.ClientSession, flow: str, n: int) -> dict[str, float]:
    text = await _text(session, ECB.format(flow=flow, n=n))
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            out[row["TIME_PERIOD"]] = float(row["OBS_VALUE"])
        except (KeyError, ValueError):
            continue
    if not out:
        raise ValueError(f"EZB {flow}: keine Daten")
    return out


async def fetch_euribor(session: aiohttp.ClientSession) -> dict[str, float]:
    return await _ecb(session, EURIBOR_FLOW, 48)


async def fetch_eurusd(session: aiohttp.ClientSession) -> dict[str, float]:
    return await _ecb(session, EURUSD_FLOW, 48)


async def fetch_ecb_rate(session: aiohttp.ClientSession) -> dict[str, float]:
    """Einlagensatz der EZB in % – Trade Republic verzinst Guthaben in der Regel mit diesem Satz."""
    return await _ecb(session, ECB_DFR_FLOW, 5)


async def fetch_unemployment(session: aiohttp.ClientSession, api_key: str | None = None) -> list[list]:
    """[(YYYY-MM, Quote)] chronologisch."""
    today = date.today()
    body: dict = {"seriesid": ["LNS14000000"], "startyear": str(today.year - 2), "endyear": str(today.year)}
    if api_key:
        body["registrationkey"] = api_key
    data = None
    try:
        async with session.post(BLS_V2, json=body, timeout=TIMEOUT, headers=HEADERS) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        if data.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(data.get("message"))
    except (aiohttp.ClientError, ValueError) as err:
        _LOGGER.debug("BLS v2 fehlgeschlagen (%s), versuche v1", err)
        async with session.get(BLS_V1, timeout=TIMEOUT, headers=HEADERS) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    out = []
    for item in data["Results"]["series"][0]["data"]:
        period = item.get("period", "")
        if not period.startswith("M") or period == "M13":
            continue
        try:
            out.append([f"{item['year']}-{period[1:]}", float(item["value"])])
        except (KeyError, ValueError):
            continue
    if not out:
        raise ValueError("BLS: keine Daten")
    return sorted(out)


async def fetch_claims(session: aiohttp.ClientSession) -> list[list]:
    """[(YYYY-MM-DD Wochenende, Erstanträge)] chronologisch."""
    start = date(date.today().year - 2, 1, 1).isoformat()
    text = await _text(session, FRED_CLAIMS.format(start=start))
    out = []
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    for row in reader:
        try:
            out.append([row[0], float(row[1])])
        except (IndexError, ValueError):
            continue
    if not out:
        raise ValueError("Erstanträge: keine Daten")
    return sorted(out)


async def fetch_yield_curve(session: aiohttp.ClientSession) -> list[list]:
    """[(YYYY-MM-DD, 10 J. − 3 M.)] chronologisch, die letzten drei Kalenderjahre."""
    out = []
    year = date.today().year
    for y in (year - 2, year - 1, year):
        try:
            text = await _text(session, TREASURY.format(year=y))
        except aiohttp.ClientError:
            if y == year:
                raise
            continue
        for row in csv.DictReader(io.StringIO(text)):
            try:
                m, d, yy = row["Date"].split("/")
                spread = float(row["10 Yr"]) - float(row["3 Mo"])
            except (KeyError, ValueError):
                continue
            out.append([f"{yy}-{m}-{d}", round(spread, 4)])
    if not out:
        raise ValueError("Treasury: keine Daten")
    return sorted(out)


FETCHERS = {
    "euribor": fetch_euribor,
    "eurusd": fetch_eurusd,
    "unemployment": fetch_unemployment,
    "claims": fetch_claims,
    "yield_curve": fetch_yield_curve,
    "ecb_rate": fetch_ecb_rate,
}
