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
import re
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

_LOGGER = logging.getLogger(__name__)

HOST = "https://api.traderepublic.com"
WS_URL = "wss://api.traderepublic.com"
APP_VERSION = "2.2641.2"  # Rückfall; die aktuelle Version liest detect_app_version() von app.traderepublic.com
WEB_APP = "https://app.traderepublic.com"
_app_version: dict[str, Any] = {"value": APP_VERSION, "at": 0.0}


async def detect_app_version(session: aiohttp.ClientSession) -> str:
    """Die Version der TR-Web-App (Trade Republic lehnt veraltete ab). Einmal am Tag aus dem Web-Bundle gelesen."""
    if time.time() - _app_version["at"] < 24 * 3600:
        return _app_version["value"]
    _app_version["at"] = time.time()  # auch bei Fehlern erst morgen wieder versuchen
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(f"{WEB_APP}/", headers={"User-Agent": USER_AGENT}, timeout=timeout) as resp:
            html = await resp.text()
        m = re.search(r'src="(/assets/index-[^"]+\.js)"', html)
        if m:
            async with session.get(f"{WEB_APP}{m.group(1)}", headers={"User-Agent": USER_AGENT}, timeout=timeout) as resp:
                js = await resp.text()
            v = re.search(r"SENTRY_RELEASE=\{id:`([0-9][0-9.]+)`\}", js)
            if v:
                _app_version["value"] = v.group(1)
    except Exception as err:  # noqa: BLE001 – ohne Web-Version gilt der Rückfall, der Login versucht es trotzdem
        _LOGGER.debug("TR-Web-Version nicht gelesen: %s", err)
    return _app_version["value"]
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
    "CLIENT_VERSION_OUTDATED": "Trade Republic verlangt eine neuere Web-Version – bitte ein Update der App abwarten.",
    "NUMBER_INVALID": "Die Telefonnummer ist ungültig.",
    "LOGIN_NOT_ALLOWED": "Der Web-Login ist für dieses Konto nicht freigeschaltet.",
    "WEBTRADING_NOT_AVAILABLE": "Der Web-Login ist für dieses Konto nicht freigeschaltet.",
}
# Antworten auf den Authenticator-Code, die „Code nicht angenommen“ bedeuten
CODE_REJECTED = {"AUTHENTICATION_ERROR", "VALIDATION_CODE_INVALID", "INVALID_VALUE"}


def _tz_offset() -> int:
    """Wie JavaScripts getTimezoneOffset() für Europe/Berlin: −60 im Winter, −120 im Sommer."""
    off = datetime.now(ZoneInfo("Europe/Berlin")).utcoffset()
    return -int(off.total_seconds() // 60) if off else -60


class TRError(Exception):
    """Allgemeiner Fehler."""


class TRAuthError(TRError):
    """Login fehlt oder ist abgelaufen."""


class TRCodeRequired(TRError):
    """Trade Republic verlangt (noch) den Code aus der Authenticator-App."""


class TRCodeRejected(TRError):
    """Der Authenticator-Code wurde nicht angenommen – der Login-Vorgang bleibt offen, ein neuer Code geht."""


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
        self._qr_challenge: str | None = None

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
                "timezoneOffset": _tz_offset(),
                "screen": "1920x1080x24",
                "preferredLanguages": ["de"],
                "numberOfCores": 4,
            }
            h["X-TR-Device-Info"] = base64.b64encode(json.dumps(device).encode()).decode()
            h["X-TR-App-Version"] = _app_version["value"]
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
    def _error_code(body: Any) -> tuple[str, str]:
        """(errorCode, errorMessage) einer TR-Fehlerantwort ``{"errors": [{…}]}``."""
        try:
            err = body["errors"][0]
            return str(err.get("errorCode") or ""), str(err.get("errorMessage") or err.get("message") or "")
        except (KeyError, IndexError, TypeError, AttributeError):
            return "", ""

    @classmethod
    def _login_error(cls, status: int, body: Any, step: str = "login") -> TRError:
        code, message = cls._error_code(body)
        # Für die Fehlersuche: was Trade Republic geantwortet hat (ohne Nummer, PIN oder Code)
        _LOGGER.warning("Trade-Republic-Login (%s): HTTP %s %s %s", step, status, code or "-", message[:200])
        if status == 426:
            return TRError(LOGIN_ERRORS["CLIENT_VERSION_OUTDATED"])
        if not code:
            return TRError(f"Login fehlgeschlagen (HTTP {status}).")
        return TRError(LOGIN_ERRORS.get(code, f"Login fehlgeschlagen: {code}{' – ' + message if message else ''}"))

    # ----------------------------------------------------------------- Login

    async def login_start(self, phone: str, pin: str) -> str:
        """Startet den Web-Login. Ergebnis: 'AUTHENTICATOR_VERIFICATION' oder 'APP_CONFIRMATION'."""
        await detect_app_version(self._session)
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
            raise self._login_error(status, body, "Status")
        return body or {}

    async def _wait_for_session(self, wait: float, code_sent: bool) -> None:
        """Fragt den Login-Vorgang ab, bis Trade Republic die Session-Cookies setzt (wie die Web-App)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        while not self.cookies.get("tr_session"):
            process = await self._process()
            st = process.get("status")
            if process.get("requiredAction") == "AUTHENTICATOR_VERIFICATION" and st == "PENDING" and not code_sent:
                self.required_action = "AUTHENTICATOR_VERIFICATION"
                raise TRCodeRequired("Trade Republic verlangt den Code aus der Authenticator-App.")
            if st not in (None, "PENDING", "CONFIRMED", "COMPLETED"):
                raise TRError(f"Login abgelehnt (Status {st}).")
            if self.cookies.get("tr_refresh") and not self.cookies.get("tr_session"):
                # manche Antworten setzen nur tr_refresh – die Session holt der nächste Aufruf
                try:
                    await self.refresh_session()
                except TRError:
                    pass
                if self.cookies.get("tr_session"):
                    break
            if loop.time() > deadline:
                raise TRAuthError("Noch nicht in der Trade-Republic-App bestätigt.")
            await asyncio.sleep(2)

    # ---------------------------------------------------------- QR-Login

    async def qr_start(self) -> dict:
        """Startet den QR-Login (ohne PIN): Trade Republic liefert eine Challenge, deren QR-Code die TR-App scannt."""
        await detect_app_version(self._session)
        self.cookies.clear()
        status, body = await self._request("POST", "/api/v2/auth/web/login/qr-challenges", login=True, json={})
        if status >= 400 or not isinstance(body, dict) or not body.get("challengeId"):
            raise self._login_error(status, body, "QR")
        self._qr_challenge = body["challengeId"]
        return body

    async def qr_poll(self) -> dict:
        """Status der Challenge: {status: PENDING|CLAIMED|EXPIRED, qrCodePayload, processId, …}.

        Der QR-Inhalt wechselt alle paar Sekunden (Token mit kurzer Laufzeit), deshalb regelmäßig abfragen.
        """
        if not self._qr_challenge:
            raise TRError("QR-Login wurde nicht gestartet.")
        status, body = await self._request("GET", f"/api/v2/auth/web/login/qr-challenges/{self._qr_challenge}",
                                           login=True)
        if status >= 400:
            code, _ = self._error_code(body)
            if code == "PROCESS_GONE" or status in (404, 410):
                return {"status": "EXPIRED"}
            if code == "TOO_MANY_REQUESTS" or status == 429:
                return {"status": "PENDING", "throttled": True}
            raise self._login_error(status, body, "QR-Status")
        body = body if isinstance(body, dict) else {}
        if body.get("status") == "CLAIMED" and body.get("processId"):
            self._process_id = body["processId"]
        return body

    async def qr_complete(self, wait: float = 120.0) -> None:
        """Nach dem Scannen: warten, bis die Anmeldung in der TR-App bestätigt ist und die Session steht."""
        if not self._process_id:
            raise TRError("Der QR-Code wurde noch nicht gescannt.")
        await self._wait_for_session(wait, code_sent=True)
        await self.account()

    async def login_complete(self, code: str | None = None, wait: float = 20.0) -> None:
        """Schließt den Login ab: per Authenticator-Code oder Bestätigung in der TR-App."""
        if not self._process_id:
            raise TRError("Login wurde nicht gestartet.")
        code_sent = False
        if code is not None or self.required_action == "AUTHENTICATOR_VERIFICATION":
            code = re.sub(r"\D", "", code or "")
            if not 4 <= len(code) <= 8:
                raise TRCodeRejected("Bitte den 6-stelligen Code aus der Authenticator-App eingeben.")
            status, body = await self._request(
                "POST", f"/api/v2/auth/web/login/processes/{self._process_id}/authenticator-verification",
                login=True, json={"code": code})
            if status >= 400:
                err = self._login_error(status, body, "Code")
                if self._error_code(body)[0] in CODE_REJECTED or status in (400, 401):
                    raise TRCodeRejected("Der Code wurde nicht angenommen (falsch oder schon abgelaufen). "
                                         "Bitte den aktuellen Code aus der Authenticator-App eingeben.") from err
                raise err
            code_sent = True
        await self._wait_for_session(wait, code_sent)
        await self.account()

    async def refresh_session(self) -> None:
        status, _ = await self._request("GET", "/api/v1/auth/web/session")
        if status in (401, 403):
            raise TRAuthError("Trade-Republic-Session abgelaufen.")
        if status >= 400:
            raise TRError(f"Session-Verlängerung fehlgeschlagen (HTTP {status}).")

    async def logout(self) -> None:
        """Beendet die Session bei Trade Republic und vergisst die Cookies (Fehler sind egal)."""
        if self.cookies:
            try:
                await self._request("POST", "/api/v1/auth/web/logout", login=True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("TR-Logout: %s", err)
        self.cookies = {}

    async def account(self) -> dict:
        status, body = await self._request("GET", "/api/v2/auth/account")
        if status in (401, 403):
            raise TRAuthError("Nicht eingeloggt.")
        if status >= 400 or not isinstance(body, dict):
            raise TRError(f"Konto konnte nicht geladen werden (HTTP {status}).")
        if body.get("securitiesAccountNumber"):
            self.sec_acc_no = body["securitiesAccountNumber"]
        return body

    async def interest(self) -> float | None:
        """Aktueller Zinssatz auf das Guthaben bei Trade Republic als Anteil (0,02 = 2 % p. a.), sonst None."""
        status, body = await self._request("GET", "/api/v1/interest/details")
        if status in (401, 403):
            raise TRAuthError("Nicht eingeloggt.")
        if status >= 400 or not isinstance(body, (dict, list)):
            _LOGGER.info("TR-Zinssatz nicht verfügbar (HTTP %s)", status)
            return None
        rate = find_rate(body)
        if rate is None:
            _LOGGER.info("TR-Zinssatz nicht erkannt, Felder: %s", sorted(body)[:30] if isinstance(body, dict) else "Liste")
        return rate

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
        # Wie die Web-App: zuerst V2, dann die älteren Varianten als Rückfall
        res = await self.fetch([
            {"type": "compactPortfolioByTypeV2", "secAccNo": self.sec_acc_no},
            {"type": "cash"},
        ], auth=True)
        port, cash = res
        if isinstance(port, TRAuthError):
            raise port
        for fallback in ({"type": "compactPortfolioByType", "secAccNo": self.sec_acc_no}, {"type": "compactPortfolio"}):
            if not isinstance(port, Exception):
                break
            (port,) = await self.fetch([fallback], auth=True)
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
            avg = _f(_amount(p.get("averageBuyIn")))
            if isin in positions:  # dieselbe ISIN in mehreren Kategorien: zusammenfassen
                prev = positions[isin]
                total = prev["size"] + size
                known = avg is not None and prev["avg_buy"] is not None and total
                positions[isin] = {**prev, "size": total,
                                   "avg_buy": (prev["avg_buy"] * prev["size"] + avg * size) / total if known else None}
            else:
                positions[isin] = {"size": size, "avg_buy": avg}
            # Was Trade Republic selbst als Gewinn seit Kauf zeigt (falls mitgeliefert) – zum Abgleich
            net = _f(_amount(p.get("netValue")))
            if net is not None:  # Wert laut Trade Republic
                positions[isin]["tr_value"] = (positions[isin].get("tr_value") or 0) + net
            perf = _f(_amount(p.get("performanceSinceBuyAbsolute")))
            if perf is not None:
                positions[isin]["tr_pnl"] = (positions[isin].get("tr_pnl") or 0) + perf
        for isin, pos in positions.items():
            _LOGGER.info("TR-Position %s: %s Stück, Kaufkurs Ø %s, Wert laut TR %s", isin, pos["size"],
                         pos["avg_buy"], pos.get("tr_value"))
        cash_eur = None
        if not isinstance(cash, Exception) and isinstance(cash, list):
            for c in cash:
                if c.get("currencyId") == "EUR":
                    cash_eur = _f(c.get("amount"))
        return {"positions": positions, "cash": cash_eur}


def _amount(v: Any) -> Any:
    """Betrag als Zahl oder als ``{"value": …, "currency": …}`` (neuere TR-Antworten)."""
    return v.get("value") if isinstance(v, dict) else v


RATE_KEYS = ("interestRate", "rate", "currentInterestRate", "effectiveInterestRate", "annualRate", "apy")


def find_rate(body: Any, depth: int = 0) -> float | None:
    """Sucht den Zinssatz in der Antwort; Prozentangaben (2.0) werden zu Anteilen (0,02)."""
    if depth > 4:
        return None
    if isinstance(body, dict):
        for k in RATE_KEYS:
            if k in body:
                v = _f(_amount(body[k]))
                if v is not None and 0 <= v < 25:
                    return v / 100 if v >= 0.25 else v
        for v in body.values():
            if isinstance(v, (dict, list)):
                r = find_rate(v, depth + 1)
                if r is not None:
                    return r
    elif isinstance(body, list):
        for v in body:
            r = find_rate(v, depth + 1)
            if r is not None:
                return r
    return None


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
