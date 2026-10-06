"""Schlanker Trade-Republic-Client (Web-Login v2 + WebSocket) auf Basis von aiohttp.

Öffentliche Daten (Kerzen, Kurse, Instrumente) brauchen keinen Login. Für das Depot
wird die Web-Session (Cookies) genutzt, die beim einmaligen Login entsteht und
danach über /api/v1/auth/web/session regelmäßig verlängert wird.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

HOST = "https://api.traderepublic.com"
WS_URL = "wss://api.traderepublic.com"
APP_VERSION = "2.2631.13"
WEB_PLATFORM = "web-pro"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
CONNECT_MSG = {
    "locale": "de",
    "platformId": "webtrading",
    "platformVersion": "chrome - 146.0.0",
    "clientId": "app.traderepublic.com",
    "clientVersion": "5582",
}

LOGIN_ERRORS = {
    "PROCESS_GONE": "Die Login-Anfrage ist abgelaufen. Bitte neu starten.",
    "ALREADY_PROCESSED": "Die Login-Anfrage wurde abgelehnt oder schon verwendet.",
    "NOT_FOUND": "Trade Republic kennt diese Login-Anfrage nicht.",
    "TOO_MANY_REQUESTS": "Zu viele Versuche. Bitte kurz warten.",
    "VALIDATION_CODE_INVALID": "Der Code ist nicht korrekt.",
    "VALIDATION_CODE_ALREADY_USED": "Der Code wurde bereits verwendet.",
}


class TRError(Exception):
    """Allgemeiner Fehler."""


class TRAuthError(TRError):
    """Login fehlt oder ist abgelaufen."""


class TradeRepublic:
    """Ein TR-Client. Cookies werden als einfaches dict geführt und persistiert."""

    def __init__(self, session: aiohttp.ClientSession, cookies: dict[str, str] | None = None,
                 device_id: str | None = None, sec_acc_no: str | None = None) -> None:
        self._session = session
        self.cookies: dict[str, str] = dict(cookies or {})
        self.device_id = device_id or hashlib.sha512(uuid.uuid4().bytes).hexdigest()
        self.sec_acc_no = sec_acc_no
        self._process_id: str | None = None
        self.required_action: str | None = None

    # ------------------------------------------------------------------ HTTP

    @property
    def logged_in(self) -> bool:
        return bool(self.cookies.get("tr_refresh") or self.cookies.get("tr_session"))

    def _headers(self, login: bool = False) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if login:
            device = {
                "stableDeviceId": self.device_id,
                "browser": "Chrome",
                "browserVersion": "146.0.0.0",
                "os": "Linux",
                "osVersion": "6",
                "timezone": "Europe/Berlin",
                "timezoneOffset": -60,
                "screen": "1920x1080x24",
                "preferredLanguages": ["de"],
                "numberOfCores": 4,
            }
            h["X-TR-Device-Info"] = base64.b64encode(json.dumps(device).encode()).decode()
            h["X-TR-App-Version"] = APP_VERSION
            h["X-Tr-Platform"] = WEB_PLATFORM
            h["Accept-Language"] = "de"
        return h

    def _store_cookies(self, resp: aiohttp.ClientResponse) -> None:
        for name, morsel in resp.cookies.items():
            if morsel.value:
                self.cookies[name] = morsel.value
            else:
                self.cookies.pop(name, None)

    async def _request(self, method: str, path: str, *, login: bool = False, **kw: Any) -> tuple[int, Any]:
        async with self._session.request(method, f"{HOST}{path}", headers=self._headers(login),
                                         timeout=aiohttp.ClientTimeout(total=30), **kw) as resp:
            self._store_cookies(resp)
            try:
                body = await resp.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError):
                body = None
            return resp.status, body

    @staticmethod
    def _login_error(status: int, body: Any) -> TRError:
        try:
            code = body["errors"][0]["errorCode"]
        except (KeyError, IndexError, TypeError):
            return TRError(f"Login fehlgeschlagen (HTTP {status}).")
        return TRError(LOGIN_ERRORS.get(code, f"Login fehlgeschlagen: {code}"))

    # ----------------------------------------------------------------- Login

    async def login_start(self, phone: str, pin: str) -> str:
        """Startet den Web-Login. Ergebnis: 'AUTHENTICATOR_VERIFICATION' oder 'APP_CONFIRMATION'."""
        self.cookies.clear()
        status, body = await self._request("POST", "/api/v2/auth/web/login", login=True,
                                           json={"phoneNumber": phone, "pin": pin})
        if status >= 400 or not isinstance(body, dict) or not body.get("processId"):
            raise self._login_error(status, body)
        self._process_id = body["processId"]
        process = await self._process()
        self.required_action = process.get("requiredAction")
        return "AUTHENTICATOR_VERIFICATION" if self.required_action == "AUTHENTICATOR_VERIFICATION" \
            else "APP_CONFIRMATION"

    async def _process(self) -> dict:
        status, body = await self._request("GET", f"/api/v2/auth/web/login/processes/{self._process_id}", login=True)
        if status >= 400:
            raise self._login_error(status, body)
        return body or {}

    async def login_complete(self, code: str | None = None, wait: float = 20.0) -> None:
        """Schließt den Login ab: per Authenticator-Code oder Bestätigung in der TR-App."""
        if not self._process_id:
            raise TRError("Login wurde nicht gestartet.")
        if self.required_action == "AUTHENTICATOR_VERIFICATION":
            status, body = await self._request(
                "POST", f"/api/v2/auth/web/login/processes/{self._process_id}/authenticator-verification",
                login=True, json={"code": code})
            if status >= 400:
                raise self._login_error(status, body)
        else:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + wait
            while True:
                process = await self._process()
                st = process.get("status")
                if st in ("CONFIRMED", "COMPLETED"):
                    break
                if st != "PENDING":
                    raise TRError(f"Unerwarteter Login-Status: {st}")
                if loop.time() > deadline:
                    raise TRAuthError("Noch nicht in der Trade-Republic-App bestätigt.")
                await asyncio.sleep(2)
        if not self.logged_in:
            # Manche Antworten setzen die Session erst beim nächsten Aufruf
            await self.refresh_session()
        await self.account()

    async def refresh_session(self) -> None:
        status, _ = await self._request("GET", "/api/v1/auth/web/session")
        if status in (401, 403):
            raise TRAuthError("Trade-Republic-Session abgelaufen.")
        if status >= 400:
            raise TRError(f"Session-Verlängerung fehlgeschlagen (HTTP {status}).")

    async def account(self) -> dict:
        status, body = await self._request("GET", "/api/v2/auth/account")
        if status in (401, 403):
            raise TRAuthError("Nicht eingeloggt.")
        if status >= 400 or not isinstance(body, dict):
            raise TRError(f"Konto konnte nicht geladen werden (HTTP {status}).")
        if body.get("securitiesAccountNumber"):
            self.sec_acc_no = body["securitiesAccountNumber"]
        return body

    # ------------------------------------------------------------- WebSocket

    async def fetch(self, payloads: list[dict], *, auth: bool = False, timeout: float = 25.0) -> list[Any]:
        """Öffnet eine WebSocket-Verbindung, abonniert alle payloads und liefert je die erste Antwort.

        Fehlerhafte oder ausbleibende Antworten werden als Exception-Objekt zurückgegeben.
        """
        headers = {"User-Agent": USER_AGENT}
        if auth and self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        results: list[Any] = [TRError("keine Antwort")] * len(payloads)
        pending = set(range(len(payloads)))
        async with self._session.ws_connect(WS_URL, headers=headers, heartbeat=20,
                                            timeout=aiohttp.ClientWSTimeout(ws_close=10)) as ws:
            await ws.send_str(f"connect 31 {json.dumps(CONNECT_MSG)}")
            msg = await asyncio.wait_for(ws.receive(), 10)
            if msg.type != aiohttp.WSMsgType.TEXT or msg.data != "connected":
                raise TRError(f"WebSocket-Verbindung abgelehnt: {msg.data!r}")
            for i, p in enumerate(payloads):
                await ws.send_str(f"sub {i + 1} {json.dumps(p)}")
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while pending:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.receive(), remaining)
                except asyncio.TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                        break
                    continue
                sid, _, rest = msg.data.partition(" ")
                code, payload = rest[:1], rest[2:]
                if not sid.isdigit():
                    continue
                idx = int(sid) - 1
                if idx not in pending:
                    continue
                if code == "A":
                    try:
                        results[idx] = json.loads(payload) if payload else {}
                    except ValueError as err:
                        results[idx] = TRError(f"ungültige Antwort: {err}")
                    pending.discard(idx)
                    await ws.send_str(f"unsub {idx + 1}")
                elif code == "E":
                    try:
                        err = json.loads(payload)
                    except ValueError:
                        err = payload
                    text = json.dumps(err)
                    results[idx] = TRAuthError(text) if "AUTHENTICATION" in text.upper() or "UNAUTHORIZED" in \
                        text.upper() else TRError(text)
                    pending.discard(idx)
        return results

    async def market_data(self, isins: list[str], exchange: str, *, candles: bool = True,
                          names: bool = True) -> dict[str, dict]:
        """Kerzen (täglich, Range max), Ticker und Name je ISIN."""
        payloads: list[dict] = []
        index: list[tuple[str, str]] = []
        for isin in isins:
            ident = f"{isin}.{exchange}"
            payloads.append({"type": "ticker", "id": ident})
            index.append((isin, "ticker"))
            if candles:
                payloads.append({"type": "aggregateHistoryLight", "range": "max", "id": ident,
                                 "resolution": 86_400_000})
                index.append((isin, "candles"))
            if names:
                payloads.append({"type": "instrument", "id": isin})
                index.append((isin, "instrument"))
        res = await self.fetch(payloads)
        out: dict[str, dict] = {isin: {} for isin in isins}
        for (isin, kind), val in zip(index, res):
            if isinstance(val, Exception):
                _LOGGER.debug("TR %s für %s fehlgeschlagen: %s", kind, isin, val)
                continue
            if kind == "ticker":
                out[isin]["price"] = {
                    k: _f((val.get(k) or {}).get("price")) for k in ("bid", "ask", "last", "pre")
                }
            elif kind == "candles":
                out[isin]["candles"] = [{"time": a["time"], "close": a["close"]}
                                        for a in val.get("aggregates", []) if "close" in a]
            else:
                ex = next((e for e in val.get("exchanges", []) if e.get("slug") == exchange), {})
                out[isin]["name"] = val.get("shortName") or ex.get("nameAtExchange") or val.get("name")
                out[isin]["symbol"] = ex.get("symbolAtExchange")
                out[isin]["tags"] = [t.get("id") for t in val.get("tags", []) if t.get("id")]
        return out

    async def portfolio(self) -> dict:
        """Depotpositionen und Cash (Login nötig)."""
        await self.refresh_session()
        if not self.sec_acc_no:
            await self.account()
        res = await self.fetch([
            {"type": "compactPortfolioByType", "secAccNo": self.sec_acc_no},
            {"type": "cash"},
        ], auth=True)
        port, cash = res
        if isinstance(port, TRAuthError):
            raise port
        if isinstance(port, Exception):
            # Ältere Variante als Rückfall
            (port,) = await self.fetch([{"type": "compactPortfolio"}], auth=True)
            if isinstance(port, Exception):
                raise port
        positions: dict[str, dict] = {}
        raw = []
        for cat in port.get("categories", []) or []:
            raw.extend(cat.get("positions", []) or [])
        if not raw:  # ältere Variante „compactPortfolio“: flache Liste (nie beide zählen)
            raw.extend(port.get("positions", []) or [])
        for p in raw:
            isin = p.get("isin") or p.get("instrumentId")
            size = _f(p.get("netSize"))
            if not isin or not size:
                continue
            avg = _f(p.get("averageBuyIn"))
            if isin in positions:  # dieselbe ISIN in mehreren Kategorien: zusammenfassen
                prev = positions[isin]
                total = prev["size"] + size
                known = avg is not None and prev["avg_buy"] is not None and total
                positions[isin] = {"size": total,
                                   "avg_buy": (prev["avg_buy"] * prev["size"] + avg * size) / total if known else None}
            else:
                positions[isin] = {"size": size, "avg_buy": avg}
        cash_eur = None
        if not isinstance(cash, Exception) and isinstance(cash, list):
            for c in cash:
                if c.get("currencyId") == "EUR":
                    cash_eur = _f(c.get("amount"))
        return {"positions": positions, "cash": cash_eur}


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
