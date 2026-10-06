"""Engine der App: lädt Daten, trifft die Monatsentscheidung, führt das Papierdepot
und meldet neue Erkenntnisse per WhatsApp. Läuft ohne Home Assistant; der Zustand liegt in /data/state.json."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from . import strategy as S
from .const import (
    CANDLE_REFRESH_H,
    CONF_BLS_KEY,
    CONF_CASH_RATE,
    CONF_CASH_RESERVE,
    CONF_HA_SERVICE,
    CONF_HA_TARGET,
    CONF_EXTRA_ISINS,
    CONF_MONTHLY_REPORT,
    CONF_NOTIFY,
    CONF_REBALANCE_MONTH,
    CONF_SWITCH_WARNING,
    CONF_TOTAL,
    CONF_USE_DEPOT,
    CONF_WA_APIKEY,
    CONF_WA_PHONE,
    DEFAULT_REBALANCE_MONTH,
    DEFAULT_TOTAL,
    EQUIVALENT_NAMES,
    EXCHANGE,
    HISTORY_MONTHS,
    MACRO_MAX_AGE_DAYS,
    MACRO_REFRESH_H,
    MACRO_RETRY_H,
    MARKET_CLOSE,
    MARKET_OPEN,
    MONTHS_DE,
    NAME,
    ORDER_FEE,
    PILLARS,
    STATE_CASH,
    STATE_HEDGED,
    STATE_IN,
    STATE_LABELS,
    STATE_PARKED,
    TZ,
)
from .macro import FETCHERS
from .notify import send_ha_service, send_whatsapp
from .tr_api import TRAuthError, TRError, TradeRepublic

_LOGGER = logging.getLogger(__name__)

NAMES = {
    "IE00B3YLTY66": "SPDR MSCI ACWI IMI",
    "IE00BF1B7389": "SPDR MSCI ACWI EUR Hedged",
    "DE000A0S9GB0": "Xetra-Gold",
    "LU0290355717": "Xtrackers Eurozone Gov Bond",
    "LU1407888137": "Amundi US Treasury 7-10Y EUR Hedged",
}
SYMBOLS = {
    "IE00B3YLTY66": "SPYI",
    "IE00BF1B7389": "ACWI EUR Hedged",
    "DE000A0S9GB0": "4GLD",
    "LU0290355717": "XGLE",
    "LU1407888137": "US-Treasury",
}
EMOJI = {STATE_IN: "🟢", STATE_HEDGED: "🔵", STATE_PARKED: "🟦", STATE_CASH: "⚪"}
ACTION_LABELS = {"hold": "halten", "buy": "kaufen", "sell": "verkaufen", "switch": "wechseln", "cash": "in Cash"}


def _all_isins() -> list[str]:
    out: list[str] = []
    for p in PILLARS:
        for isin in [p["isin"], p.get("hedged"), *p.get("fallbacks", [])]:
            if isin and isin not in out:
                out.append(isin)
    return out


def _candidates(cfg: dict) -> set[str]:
    return {i for i in [cfg["isin"], cfg.get("hedged"), *cfg.get("fallbacks", [])] if i}


def _date_de(d: date) -> str:
    return f"{d.day}. {MONTHS_DE[d.month - 1]}"


GOLD_ISIN = "DE000A0S9GB0"  # Xetra-Gold: ein Anteil = ein Gramm Gold – sein Kurs ist der Goldpreis je Gramm
TROY_OUNCE_G = 31.1034768


def fine_grams(qty: float, unit: str, fineness: float) -> float:
    """Feingold in Gramm: Menge (g oder oz) × Feingehalt (‰, z. B. 999.9 oder 916.7)."""
    grams = qty * (TROY_OUNCE_G if unit == "oz" else 1.0)
    return grams * fineness / 1000


def normalize_phone(phone: str) -> str:
    """„0170 1234567“ → „+491701234567“."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif phone.startswith("0"):
        phone = "+49" + phone[1:]
    elif not phone.startswith("+"):
        phone = "+" + phone
    return phone


class Engine:
    """Hält den gesamten Zustand des Säulenwächters."""

    def __init__(self, data_dir: Path, options: dict, session: aiohttp.ClientSession,
                 tr_session: aiohttp.ClientSession | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "state.json"
        self._options = dict(options)
        self.tz = ZoneInfo(TZ)
        self.state: dict[str, Any] = {}
        self.data: dict | None = None
        self._http = session
        # TR braucht eine Session ohne gemeinsame Cookies (die Cookies führt der Client selbst)
        self._tr_session = tr_session or session
        self.tr = TradeRepublic(self._tr_session)
        self._login_client: TradeRepublic | None = None
        self._lock = asyncio.Lock()
        self.last_error: str | None = None
        self._qr: dict | None = None
        self.on_login = None  # async Callback nach einem Login im Hintergrund (QR): Entitäten neu senden

    def now(self) -> datetime:
        return datetime.now(self.tz)

    # ------------------------------------------------------------------ Setup

    @property
    def options(self) -> dict:
        return self._options

    @property
    def extra_isins(self) -> dict[str, list[str]]:
        """Eigene Zusatz-ISINs je Säule aus den Optionen."""
        return {key: S.parse_isins(self.options.get(opt)) for key, opt in CONF_EXTRA_ISINS.items()}

    @property
    def use_depot(self) -> bool:
        return bool(self.options.get(CONF_USE_DEPOT, True)) and (self.tr.logged_in or bool(self.snapshot))

    @property
    def snapshot(self) -> dict | None:
        """Zuletzt bei Trade Republic gelesene Positionen und Cash (die Session ist danach wieder geschlossen)."""
        return self.state.get("depot_snapshot")

    async def async_load(self) -> None:
        try:
            self.state = json.loads(self.state_file.read_text())
        except FileNotFoundError:
            self.state = {}
        except (OSError, ValueError) as err:
            _LOGGER.error("Zustand %s nicht lesbar (%s) – starte neu", self.state_file, err)
            self.state = {}
        for key in ("market", "macro", "pillars", "sent"):
            self.state.setdefault(key, {})
        self.tr = TradeRepublic(self._tr_session, cookies=self.state.get("cookies") or {},
                                device_id=self.state.get("device_id"), sec_acc_no=self.state.get("sec_acc_no"))
        self.state["device_id"] = self.tr.device_id
        self._sync_amounts()

    def _sync_amounts(self) -> None:
        total = float(self.options.get(CONF_TOTAL, DEFAULT_TOTAL))
        if self.state.get("amounts_total") != total or not self.state.get("amounts"):
            self.set_amounts({p["key"]: round(total * p["weight"], 2) for p in PILLARS}, total)

    def set_amounts(self, amounts: dict[str, float], total: float | None = None) -> None:
        """Neue Beträge. Ein geänderter Betrag verwirft den gemerkten Erlös."""
        old = self.state.get("amounts") or {}
        for key, amount in amounts.items():
            if round(old.get(key, -1), 2) != round(amount, 2):
                self.state["pillars"].setdefault(key, {})["proceeds"] = None
        self.state["amounts"] = amounts
        if total is not None:
            self.state["amounts_total"] = total

    async def async_save(self) -> None:
        self.state["cookies"] = self.tr.cookies
        self.state["sec_acc_no"] = self.tr.sec_acc_no
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, default=str))
        os.replace(tmp, self.state_file)  # atomar: nie eine halb geschriebene Datei

    # --------------------------------------------------------------- Login

    def login_status(self) -> dict:
        snap = self.snapshot or {}
        return {"logged_in": self.tr.logged_in, "phone": self.state.get("phone"),
                "synced_at": snap.get("synced_at"), "positions": len(snap.get("positions") or {}),
                "login_at": self.state.get("login_at"),
                "pending": self._login_client is not None,
                "use_depot": bool(self.options.get(CONF_USE_DEPOT, True))}

    async def login_start(self, phone: str, pin: str) -> str:
        """Startet den Web-Login mit einem eigenen Client. Ergebnis: AUTHENTICATOR_VERIFICATION oder APP_CONFIRMATION."""
        client = TradeRepublic(self._tr_session, device_id=self.state.get("device_id"))
        kind = await client.login_start(normalize_phone(phone), pin)
        self._login_client = client
        self.state["phone"] = normalize_phone(phone)
        return kind

    async def login_complete(self, code: str | None = None) -> None:
        """Schließt den Login ab und übernimmt die neue Session in den laufenden Client."""
        client = self._login_client
        if client is None:
            raise TRError("Login wurde nicht gestartet.")
        await client.login_complete(code=code.strip() if code else None, wait=25)
        async with self._lock:
            self.tr.cookies = dict(client.cookies)
            self.tr.sec_acc_no = client.sec_acc_no
            self.state["login_at"] = datetime.now(timezone.utc).isoformat()
            self.state["sent"].pop("auth", None)
            self._login_client = None
            await self.async_save()
        await self.refresh()

    # ------------------------------------------------------- Physisches Gold

    def gold_price_g(self) -> float | None:
        """Goldpreis je Gramm in Euro (Geldkurs von Xetra-Gold)."""
        return self._price(GOLD_ISIN).get("bid")

    def physical_gold(self) -> dict:
        """Selbst eingetragenes Gold mit heutigem Wert. Zählt zur Gold-Säule."""
        price = self.gold_price_g()
        items = []
        for e in self.state.get("physical_gold", []):
            value = e["fine_grams"] * price if price else None
            items.append({**e, "value": value, "pnl": value - e["cost"] if value is not None and e.get("cost") else None,
                          "cost_per_g": e["cost"] / e["fine_grams"] if e.get("cost") and e["fine_grams"] else None})
        known = [i for i in items if i["value"] is not None]
        return {"price_g": price, "items": items,
                "fine_grams": sum(i["fine_grams"] for i in items),
                "value": sum(i["value"] for i in known) if known else (0.0 if not items else None),
                "cost": sum(i.get("cost") or 0 for i in items)}

    async def add_physical_gold(self, name: str, qty: float, unit: str, fineness: float, cost: float,
                                bought: str | None = None) -> dict:
        if qty <= 0 or not 0 < fineness <= 1000 or cost < 0 or unit not in ("g", "oz"):
            raise ValueError("Menge > 0, Einheit g oder oz, Feingehalt 1–1000 ‰ und Kaufpreis ≥ 0 angeben.")
        entry = {"id": os.urandom(6).hex(), "name": (name or "Gold").strip()[:60], "qty": qty, "unit": unit,
                 "fineness": fineness, "fine_grams": round(fine_grams(qty, unit, fineness), 4),
                 "cost": round(cost, 2), "bought": bought or None, "added": self.now().isoformat()}
        async with self._lock:
            self.state.setdefault("physical_gold", []).append(entry)
            await self.async_save()
        await self.refresh()
        return entry

    async def remove_physical_gold(self, entry_id: str) -> bool:
        async with self._lock:
            before = len(self.state.get("physical_gold", []))
            self.state["physical_gold"] = [e for e in self.state.get("physical_gold", []) if e["id"] != entry_id]
            removed = len(self.state["physical_gold"]) < before
            await self.async_save()
        await self.refresh()
        return removed

    def _physical_holdings(self) -> list[dict]:
        """Physisches Gold als Bestand der Gold-Säule (nicht handelbar, keine ISIN)."""
        price = self.gold_price_g()
        return [{"isin": "PHYSISCH", "name": f"Physisches Gold · {e['name']}", "physical": True,
                 "size": e["fine_grams"], "avg_buy": e["cost"] / e["fine_grams"] if e["fine_grams"] else None,
                 "cost": e["cost"] or None, "bid": price, "value": e["fine_grams"] * price if price else None,
                 "since": e.get("bought")} for e in self.state.get("physical_gold", [])]

    # ------------------------------------------------------------ QR-Login

    async def qr_start(self) -> dict:
        """Neue QR-Challenge (ohne PIN). Die Oberfläche fragt danach qr_status() jede Sekunde ab."""
        await self.qr_cancel()
        client = TradeRepublic(self._tr_session, device_id=self.state.get("device_id"))
        await client.qr_start()
        self._qr = {"client": client, "status": "pending", "payload": None, "error": None, "task": None}
        return await self.qr_status()

    async def qr_status(self) -> dict:
        qr = getattr(self, "_qr", None)
        if not qr:
            return {"status": "none"}
        if qr["status"] == "pending":
            try:
                body = await qr["client"].qr_poll()
            except TRError as err:
                qr.update(status="error", error=str(err))
            else:
                if body.get("status") == "EXPIRED":
                    qr["status"] = "expired"
                elif body.get("status") == "CLAIMED":
                    qr["status"] = "claimed"
                    qr["task"] = asyncio.create_task(self._qr_finish(qr))
                elif body.get("qrCodePayload"):
                    qr["payload"] = body["qrCodePayload"]
        out = {"status": qr["status"], "error": qr["error"]}
        if qr["status"] == "pending" and qr["payload"]:
            out["payload"] = qr["payload"]
        return out

    async def _qr_finish(self, qr: dict) -> None:
        """Gescannt: auf die Bestätigung in der TR-App warten und die Session übernehmen."""
        client = qr["client"]
        try:
            await client.qr_complete(wait=120)
        except TRError as err:
            qr.update(status="error", error=str(err))
            return
        async with self._lock:
            self.tr.cookies = dict(client.cookies)
            self.tr.sec_acc_no = client.sec_acc_no
            self.state["login_at"] = datetime.now(timezone.utc).isoformat()
            self.state["login_method"] = "qr"
            self.state["sent"].pop("auth", None)
            await self.async_save()
        await self.refresh()  # synchronisiert und schließt die Session wieder
        qr["status"] = "done"
        if self.on_login:
            await self.on_login()

    async def qr_cancel(self) -> None:
        qr = getattr(self, "_qr", None)
        if qr and qr.get("task") and not qr["task"].done():
            qr["task"].cancel()
        self._qr = None

    async def logout(self) -> None:
        """Vergisst die gespeicherten Depotdaten – danach rechnet die App wieder mit dem Papierdepot."""
        async with self._lock:
            await self.tr.logout()
            self.state["cookies"] = {}
            self.state["login_at"] = None
            self.state.pop("depot_snapshot", None)
            await self.async_save()
        await self.refresh()

    # --------------------------------------------------------------- Update

    async def refresh(self) -> dict:
        """Ein vollständiger Durchlauf (Kurse, Wirtschaftsdaten, Depot, Entscheidung, Meldungen)."""
        try:
            self.data = await self._async_update_data()
            self.last_error = None
        except Exception as err:  # noqa: BLE001 – der Dienst läuft weiter, die Oberfläche zeigt den Fehler
            _LOGGER.exception("Aktualisierung fehlgeschlagen")
            self.last_error = str(err)
        return self.data or {}

    async def async_request_refresh(self) -> None:
        await self.refresh()

    async def _async_update_data(self) -> dict:
        async with self._lock:
            now = self.now()
            await self._update_market(now)
            await self._update_macro(now)
            depot = await self._update_depot()
            data = self._compute(now, depot)
            # Tagesverlauf nur mit echten Werten (Papierdepot oder verbundenes Depot)
            if data["mode"] == "paper" or depot.get("connected"):
                self.state["value_history"] = S.record_history(self.state.get("value_history", []),
                                                               now.date().isoformat(), data["stats"], data["mode"])
            data["value_history"] = [h for h in self.state.get("value_history", []) if h.get("mode") == data["mode"]]
            await self._notify(now, data)
            await self.async_save()
            return data

    async def _update_market(self, now: datetime) -> None:
        market = self.state["market"]
        isins = _all_isins()
        last = market.get("_candles_at")
        need_candles = (not last or now - datetime.fromisoformat(last) > timedelta(hours=CANDLE_REFRESH_H)
                        or any(not market.get(i, {}).get("candles") for i in isins))
        need_names = any(not market.get(i, {}).get("name") for i in isins)
        try:
            res = await self.tr.market_data(isins, EXCHANGE, candles=need_candles, names=need_names)
        except Exception as err:  # noqa: BLE001 – öffentliche Daten dürfen nie das Update abbrechen
            _LOGGER.warning("Kursdaten von Trade Republic nicht geladen: %s", err)
            market["_error"] = str(err)
            return
        market.pop("_error", None)
        got_candles = False
        for isin, d in res.items():
            m = market.setdefault(isin, {})
            if d.get("price"):
                m["price"] = d["price"]
                m["price_at"] = now.isoformat()
            if d.get("candles"):
                m["candles"] = d["candles"]
                got_candles = True
            for k in ("name", "symbol"):
                if d.get(k):
                    m[k] = d[k]
        if need_candles and got_candles:
            market["_candles_at"] = now.isoformat()

    async def _update_macro(self, now: datetime) -> None:
        macro = self.state["macro"]
        for key, fetch in FETCHERS.items():
            m = macro.setdefault(key, {})
            ok_at = datetime.fromisoformat(m["ok_at"]) if m.get("ok_at") else None
            tried_at = datetime.fromisoformat(m["tried_at"]) if m.get("tried_at") else None
            if ok_at and now - ok_at < timedelta(hours=MACRO_REFRESH_H):
                continue
            if tried_at and now - tried_at < timedelta(hours=MACRO_RETRY_H):
                continue
            m["tried_at"] = now.isoformat()
            try:
                if key == "unemployment":
                    m["data"] = await fetch(self._http, self.options.get(CONF_BLS_KEY) or None)
                else:
                    m["data"] = await fetch(self._http)
                m["ok_at"] = now.isoformat()
                m.pop("error", None)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Wirtschaftsdaten %s nicht geladen: %s", key, err)
                m["error"] = str(err)

    def _macro_data(self, key: str, now: datetime):
        m = self.state["macro"].get(key) or {}
        if not m.get("ok_at"):
            return None
        if now - datetime.fromisoformat(m["ok_at"]) > timedelta(days=MACRO_MAX_AGE_DAYS):
            return None
        return m.get("data")

    async def _update_depot(self) -> dict:
        """Depotdaten: frisch von Trade Republic, solange eine Session offen ist – danach wird sie geschlossen und
        es gilt der gespeicherte Stand (Stückzahlen und Cash), bewertet mit aktuellen Kursen."""
        depot: dict[str, Any] = {"connected": False, "error": None, "positions": {}, "cash": None, "synced_at": None}
        if not self.options.get(CONF_USE_DEPOT, True):
            depot["error"] = "deaktiviert"
            return depot
        if self.tr.logged_in:
            try:
                await self._sync_depot()
            except TRAuthError as err:
                depot["error"] = "auth"
                _LOGGER.warning("Trade-Republic-Login abgelaufen: %s", err)
            except Exception as err:  # noqa: BLE001
                depot["error"] = str(err)
                _LOGGER.warning("Depot nicht geladen: %s", err)
            finally:
                await self.tr.logout()  # nie verbunden bleiben
        snap = self.snapshot
        if not snap:
            depot["error"] = depot["error"] or "nicht synchronisiert"
            return depot
        depot.update(positions=copy.deepcopy(snap["positions"]), cash=snap.get("cash"),
                     synced_at=snap.get("synced_at"), connected=True)
        # Kurse für Positionen außerhalb der Säulen-Instrumente (öffentliche Kursdaten, kein Login nötig)
        extra = [i for i in depot["positions"] if i not in _all_isins()]
        if extra:
            try:
                res = await self.tr.market_data(extra, EXCHANGE, candles=False,
                                                names=any(not self.state["market"].get(i, {}).get("name")
                                                          for i in extra))
                for isin, d in res.items():
                    m = self.state["market"].setdefault(isin, {})
                    m.update({k: v for k, v in d.items() if v})
            except Exception:  # noqa: BLE001
                pass
        return depot

    async def _sync_depot(self) -> None:
        """Einmal lesen: Positionen, Cash und Zinssatz; der Stand wird gespeichert."""
        p = await self.tr.portfolio()
        # Seit wann eine Position gehalten wird: Trade Republic liefert kein Kaufdatum – gezählt wird ab dem ersten
        # Abgleich, an dem sie im Depot war (in der Oberfläche korrigierbar). Verkaufte Positionen fallen heraus.
        since = self.state.setdefault("held_since", {})
        today = self.now().date().isoformat()
        for isin in list(since):
            if isin not in p["positions"]:
                del since[isin]
        for isin in p["positions"]:
            since.setdefault(isin, {"date": today, "manual": False})
        self.state["depot_snapshot"] = {"positions": p["positions"], "cash": p.get("cash"),
                                        "synced_at": self.now().isoformat()}
        self.state["sent"].pop("auth", None)
        try:  # Zinssatz auf das Guthaben – bei jedem Abgleich neu
            rate = await self.tr.interest()
            if rate is not None:
                self.state["interest"] = {"rate": rate, "at": self.now().isoformat()}
        except Exception as err:  # noqa: BLE001
            _LOGGER.info("TR-Zinssatz nicht geladen: %s", err)

    # -------------------------------------------------------------- Rechnen

    @staticmethod
    def market_open(now: datetime) -> bool:
        if now.weekday() >= 5:
            return False
        t = (now.hour, now.minute)
        return MARKET_OPEN <= t < MARKET_CLOSE

    def _name(self, isin: str | None) -> str:
        if not isin:
            return "Cash"
        m = self.state["market"].get(isin, {})
        return NAMES.get(isin) or EQUIVALENT_NAMES.get(isin) or m.get("name") or isin

    def _price(self, isin: str) -> dict:
        return self.state["market"].get(isin, {}).get("price") or {}

    def _strategy_cash(self, depot: dict) -> float:
        """Cash bei Trade Republic, das zur Strategie gehört: alles außer der eingestellten Reserve."""
        try:
            reserve = float(self.options.get(CONF_CASH_RESERVE) or 0)
        except (TypeError, ValueError):
            reserve = 0.0
        return max((depot.get("cash") or 0.0) - reserve, 0.0)

    def cash_rate(self) -> dict:
        """Zinssatz auf Cash: eigener Wert aus den Optionen, sonst der zuletzt von Trade Republic gelesene."""
        own = self.options.get(CONF_CASH_RATE)
        if own not in (None, ""):
            try:
                return {"rate": float(str(own).replace(",", ".")) / 100, "source": "option", "at": None}
            except ValueError:
                pass
        tr = self.state.get("interest") or {}
        if tr.get("rate") is not None:
            return {"rate": tr["rate"], "source": "trade_republic", "at": tr.get("at")}
        ecb = self._macro_data("ecb_rate", self.now())
        if ecb:
            day = max(ecb)
            return {"rate": ecb[day] / 100, "source": "ezb", "at": day}
        return {"rate": None, "source": None, "at": None}

    def _accrue_interest(self, pillars: dict, amounts: dict, today: date, rate: float | None) -> None:
        """Papierdepot: Säulen in Cash bekommen täglich die Zinsen gutgeschrieben (wie bei Trade Republic)."""
        for key, p in pillars.items():
            st = p["st"]
            if (st.get("paper") or {}).get("isin"):
                st["interest_at"] = None  # investiert: keine Zinsen
                continue
            last = date.fromisoformat(st["interest_at"]) if st.get("interest_at") else None
            st["interest_at"] = today.isoformat()
            if not rate or not last or today <= last:
                continue
            base = st.get("proceeds") or amounts[key]
            gain = base * ((1 + rate) ** ((today - last).days / 365) - 1)
            st["proceeds"] = base + gain
            st["interest_earned"] = (st.get("interest_earned") or 0) + gain

    def _compute(self, now: datetime, depot: dict) -> dict:
        today = now.date()
        current_month = S.month_key(today)
        market = self.state["market"]
        closes = {isin: S.monthly_closes(m.get("candles") or [], today)
                  for isin, m in market.items() if not isin.startswith("_")}
        macro_rows = {
            "unemployment": S.eval_unemployment(self._macro_data("unemployment", now)),
            "claims": S.eval_claims(self._macro_data("claims", now), today),
            "yield_curve": S.eval_yield_curve(self._macro_data("yield_curve", now), today),
        }
        ctx = {
            "today": today,
            "closes": closes,
            "euribor": self._macro_data("euribor", now),
            "eurusd": self._macro_data("eurusd", now),
            "macro": macro_rows,
            "names": {i: self._name(i) for i in _all_isins()},
            "symbols": SYMBOLS,
            "prices": {i: self._price(i) for i in _all_isins()},
        }
        amounts = self.state["amounts"]
        is_open = self.market_open(now)
        mode = "depot" if self.use_depot else "paper"
        events: list[dict] = []
        pillars: dict[str, dict] = {}

        # 1) Auswertung und Monatsentscheidung
        for cfg in PILLARS:
            key = cfg["key"]
            st = self.state["pillars"].setdefault(key, {})
            res = S.evaluate_pillar(cfg, ctx, st)
            sig = S.decision_signature(cfg, amounts[key])
            if res["ready"] and (st.get("month") != current_month or st.get("signature") != sig) \
                    and (is_open or not st.get("month")):
                prev_target = st.get("target") if st.get("month") else None
                first = not st.get("month")
                st.update({
                    "month": current_month,
                    "signature": sig,
                    "sma_on_prev": st.get("sma_on"),
                    "sma_on": res["sma"]["on"] if res.get("sma") else None,
                    "trend_on": res["trend_on"],
                    "state": res["state"],
                    "prev_target": prev_target,
                    "target": res["target"],
                    "target_name": self._name(res["target"]) if res["target"] else None,
                    "reason": res.get("recession_reason"),
                    "decided_at": now.isoformat(),
                })
                hist = [h for h in st.get("history", []) if h["month"] != current_month]
                hist.append({"month": current_month, "state": res["state"], "name": st["target_name"]})
                st["history"] = hist[-HISTORY_MONTHS:]
                events.append({"type": "decision", "key": key, "first": first,
                               "changed": first or prev_target != res["target"]})
            pillars[key] = {"cfg": cfg, "res": res, "st": st}

        # 2) Papierdepot ausführen (nur ohne echtes Depot)
        phys = self._physical_holdings()
        phys_value = sum(h["value"] or 0 for h in phys)
        gold_key = next((k for k, p in pillars.items() if p["cfg"]["isin"] == GOLD_ISIN), None)
        rate = self.cash_rate()
        if mode == "paper":
            self._accrue_interest(pillars, amounts, today, rate["rate"])
        if mode == "paper" and is_open:
            for key, p in pillars.items():
                amount = amounts[key] - phys_value if key == gold_key else amounts[key]
                self._paper_execute(key, p["st"], amount, now)

        # 3) Bestände je Säule
        unassigned: list[dict] = []
        if mode == "depot":
            holdings, unassigned = self._allocate(pillars, depot)
        else:
            holdings = self._paper_holdings(pillars)
        if gold_key and phys:
            holdings.setdefault(gold_key, []).extend(phys)

        # 4) Werte, Aktion, Status
        values: dict[str, float] = {}
        out_pillars: dict[str, dict] = {}
        # Echtes Depot: Säulen ohne Position halten ihren Anteil am Cash bei Trade Republic –
        # nicht den konfigurierten Betrag, der im Depot gar nicht existiert.
        empty = [k for k in pillars if not holdings.get(k)]
        empty_soll = sum(amounts[k] for k in empty) or 1
        depot_cash = self._strategy_cash(depot)
        # Echtes Depot: Säulenbeträge immer als Anteil am tatsächlichen Depot (40/30/30 vom Ist-Gesamtwert),
        # der eingestellte Gesamtbetrag zählt nur für das Papierdepot.
        base = dict(amounts)
        if mode == "depot":
            depot_total = depot_cash + sum(h.get("value") or 0 for hs in holdings.values() for h in hs)
            weight_sum = sum(amounts.values()) or 1
            base = {k: depot_total * amounts[k] / weight_sum for k in amounts}
        for key, p in pillars.items():
            cfg, res, st = p["cfg"], p["res"], p["st"]
            held = holdings.get(key, [])
            if held and all(h.get("value") is not None for h in held):
                value = sum(h["value"] for h in held)
            elif mode == "depot":
                value = depot_cash * amounts[key] / empty_soll if not held else 0.0
            else:
                value = st.get("proceeds") or amounts[key]
            values[key] = value
            target = st.get("target") if st.get("month") else None
            tradable = [h for h in held if not h.get("physical")]
            physical_value = sum(h.get("value") or 0 for h in held if h.get("physical"))
            # Kaufbetrag: was das physische Gold nicht schon abdeckt
            buy_budget = max((base[key] if mode == "depot" else (st.get("proceeds") or amounts[key]))
                             - physical_value, 0.0)
            action = S.plan_action([h.get("counts_as") or h["isin"] for h in tradable], target) \
                if st.get("month") else None
            if action == "buy" and buy_budget < 2 * ORDER_FEE:
                action = "hold"  # die Säule ist mit physischem Gold schon gedeckt
            if mode == "depot" and not depot.get("connected"):
                action = None  # ohne Depotdaten keine Handlungsanweisung
            quote = self._price(cfg["isin"])
            price = quote.get("last")
            out_pillars[key] = {
                "key": key,
                "name": cfg["name"],
                "color": cfg["color"],
                "isin": cfg["isin"],
                "instrument": self._name(cfg["isin"]),
                "signal_type": cfg["signal"],
                "price": price,
                "change_24h": price / quote["pre"] - 1 if price and quote.get("pre") else None,
                "ready": res["ready"],
                "months_have": res.get("months_have"),
                "months_need": res.get("months_need"),
                "decision_month": st.get("month"),
                "state": st.get("state"),
                "state_label": STATE_LABELS.get(st.get("state"), "–"),
                "trend_on": st.get("trend_on"),
                "target": target,
                "target_name": st.get("target_name"),
                "prev_target": st.get("prev_target"),
                "prev_target_name": self._name(st.get("prev_target")),
                "reason": st.get("reason"),
                "live_state": res.get("state"),
                "signals": self._signal_rows(res, st, today),
                "switch": res.get("switch"),
                "switch_dir": res.get("switch_dir"),
                "would_flip": S.would_flip(res, price),
                "hurdle": res.get("hurdle"),
                "hurdle_source": res.get("hurdle_source"),
                "close_month": res.get("close_month"),
                "close": res.get("close"),
                "held": held,
                "physical_value": physical_value or None,
                "buy_budget": buy_budget,
                "value": value,
                "amount": round(base[key], 2),
                "proceeds": st.get("proceeds"),
                "action": action,
                "action_label": ACTION_LABELS.get(action, "–") if action else "–",
                "history": st.get("history", []),
            }
            out_pillars[key]["status"] = self._status_text(out_pillars[key], res, today)
            # Handlungsbedarf im echten Depot: die genaue Anweisung für die Karte
            out_pillars[key]["instruction"] = (self._instruction(out_pillars[key], False)
                                               if mode == "depot" and action in ("buy", "sell", "switch") else None)

        overview = S.pillars_overview(values, amounts)
        # Verteilung bei Trade Republic: nur erkannte Positionen + Cash, gegen das Soll laut Strategie
        split = None
        if mode == "paper" or depot.get("connected"):
            tr_values = {k: sum(h.get("value") or 0 for h in holdings.get(k, [])) for k in pillars}
            soll = {r["key"]: r["soll"] for r in overview["rows"]}
            targets = {k: (p["st"].get("target") if p["st"].get("month") else p["res"].get("target"))
                       for k, p in pillars.items()}
            # Papierdepot: Cash ist, was die Säulen ohne Position gerade halten (Erlös bzw. Betrag)
            cash = self._strategy_cash(depot) if mode == "depot" else sum(values[k] for k in pillars if not holdings.get(k))
            split = S.tr_split(tr_values, targets, soll, cash,
                               sum(u.get("value") or 0 for u in unassigned),
                               {k: [{"isin": h["isin"], "name": h["name"], "value": h.get("value") or 0}
                                    for h in holdings.get(k, [])] for k in pillars})
            split["source"] = mode
        for row in overview["rows"]:
            row["name"] = out_pillars[row["key"]]["name"]
            row["color"] = out_pillars[row["key"]]["color"]
            out_pillars[row["key"]].update(ist=row["ist"], soll=row["soll"], diff_pp=row["diff_pp"],
                                           target_value=row["target_value"])

        # Alles, was jetzt im Depot geändert werden muss (rot oben in der Karte)
        todo = [{"key": k, "name": p["name"], "action": p["action"], "action_label": p["action_label"],
                 "text": p["instruction"]} for k, p in out_pillars.items() if p.get("instruction")]
        if overview["due"] and not todo:
            todo.append({"key": "rebalance", "name": "Depot", "action": "rebalance", "action_label": "angleichen",
                         "text": "ANGLEICHEN: " + " · ".join(
                             f"{out_pillars[r['key']]['name']} {S.fmt_eur(r['value'], 0)} → {S.fmt_eur(r['target_value'], 0)}"
                             for r in overview["rows"] if abs(r["diff_pp"]) >= 0.5),
                         "rows": [{"key": r["key"], "name": out_pillars[r["key"]]["name"],
                                   "value": round(r["value"], 2), "target_value": round(r["target_value"], 2),
                                   "delta": round(r["target_value"] - r["value"], 2),
                                   "ist": r["ist"], "soll": r["soll"],
                                   "cash": out_pillars[r["key"]]["state"] == STATE_CASH}
                                  for r in overview["rows"]]})
        stats = S.pillar_stats([{"key": k, "name": p["name"], "value": p["value"], "held": p["held"]}
                                for k, p in out_pillars.items()])
        # Zinsen auf Cash: im Depot das Guthaben bei TR, im Papierdepot die Säulen ohne Position
        cash_base = (depot.get("cash") or 0.0) if mode == "depot" else \
            sum(values[k] for k in pillars if not holdings.get(k))
        stats["interest"] = {
            **rate, "cash": round(cash_base, 2),
            "per_year": round(cash_base * rate["rate"], 2) if rate["rate"] is not None else None,
            "earned": round(sum(p["st"].get("interest_earned") or 0 for p in pillars.values()), 2)
            if mode == "paper" else None}
        return {
            "updated": now.isoformat(),
            "mode": mode,
            "stats": stats,
            "physical_gold": self.physical_gold(),
            "todo": todo,
            "market_open": is_open,
            "next_check": S.next_check_date(today).isoformat(),
            "pillars": out_pillars,
            "overview": overview,
            "macro": macro_rows,
            "dollar": S.eval_dollar(ctx["eurusd"], S.add_months(current_month, -1)),
            "depot": {
                "connected": depot.get("connected", False),
                "error": depot.get("error"),
                "cash": depot.get("cash"),
                "positions": {i: {**p, "name": self._name(i), "bid": self._price(i).get("bid"),
                                  "counts_as": S.resolve_isin(i, PILLARS, self.extra_isins)}
                              for i, p in (depot.get("positions") or {}).items()},
                "unassigned": unassigned,
                "synced_at": depot.get("synced_at"),
            },
            "tr_split": split,
            "reconcile": self._reconcile(depot, holdings, unassigned) if mode == "depot" else None,
            "market_error": market.get("_error"),
            "macro_status": {k: {"ok_at": v.get("ok_at"), "error": v.get("error")}
                             for k, v in self.state["macro"].items()},
            "events": events,
        }

    def _signal_rows(self, res: dict, st: dict, today: date) -> list[dict]:
        rows = copy.deepcopy(res.get("signals") or [])
        if rows and rows[0]["key"] == "decision" and st.get("month"):
            # Die Entscheidung gilt für den ganzen Monat – angezeigt wird die gespeicherte.
            state = st.get("state")
            rows[0].update(state="on" if state in (STATE_IN, STATE_HEDGED) else "off",
                           title=f"Entscheidung {S.month_label(st['month'])}",
                           value=STATE_LABELS.get(state, "–").lower() if state != STATE_CASH else "Cash",
                           hint=st.get("reason") or None)
        return rows

    def _status_text(self, p: dict, res: dict, today: date) -> str:
        nxt = _date_de(S.next_check_date(today))
        if not res["ready"]:
            return f"Warte auf Daten · {res.get('status', '')}"
        if not p["decision_month"]:
            return "Entscheidung folgt zur Handelszeit"
        close = f"Schluss {S.month_label(res['close_month'])} {S.fmt_eur(res['close'])}"
        action, target_name = p["action"], p["target_name"]
        if action == "buy":
            if p["state"] == STATE_PARKED:
                return f"Trend abwärts – weiche aus in {target_name}"
            if p["state"] == STATE_HEDGED:
                return f"Trend aufwärts – kaufe die währungsgesicherte Variante {target_name}"
            return "Trend aufwärts – kaufe"
        if action == "sell":
            return "Trend abwärts – verkaufe"
        if action == "switch":
            return f"Wechsel zu {target_name}"
        if action == "cash" or p["state"] == STATE_CASH:
            return f"In Cash · {close} · nächste Prüfung {nxt}"
        profit = self._profit(p)
        profit_txt = f" {S.fmt_pct(profit)}" if profit is not None else ""
        if p["state"] == STATE_PARKED:
            return f"Ausgewichen in {target_name}{profit_txt} · {close} · nächste Prüfung {nxt}"
        if p["state"] == STATE_HEDGED:
            return f"Investiert in {target_name}{profit_txt} · {close} · nächste Prüfung {nxt}"
        return f"Investiert{profit_txt} · {close} · nächste Prüfung {nxt}"

    @staticmethod
    def _profit(p: dict) -> float | None:
        cost = sum(h.get("cost") or 0 for h in p["held"])
        value = sum(h.get("value") or 0 for h in p["held"])
        return value / cost - 1 if cost else None

    # ------------------------------------------------------ Bestände/Depot

    def _allocate(self, pillars: dict, depot: dict) -> tuple[dict[str, list[dict]], list[dict]]:
        """Erkennt die echten Depotpositionen anhand der ISIN und ordnet sie den Säulen zu.

        Jede ISIN wird erst auf das Säulen-Instrument abgebildet, für das sie zählt (sie selbst, ein
        gleichwertiges Produkt aus dem Katalog oder eine eigene Zusatz-ISIN). Dieses Instrument gehört zu
        den Säulen, deren Ziel (oder Ziel des Vormonats) es ist; sonst zur Säule, deren eigenes Instrument
        es ist. Teilen sich mehrere Säulen ein Instrument (z. B. XGLE als Anleihen-Säule und als
        Ausweichziel), wird nach Beträgen aufgeteilt. Was nicht erkannt wird, landet in der zweiten Liste.
        """
        amounts = self.state["amounts"]
        extras = self.extra_isins
        out: dict[str, list[dict]] = {k: [] for k in pillars}
        unassigned: list[dict] = []
        for isin, pos in (depot.get("positions") or {}).items():
            bid = self._price(isin).get("bid")
            if not bid and pos.get("tr_value") and pos.get("size"):
                bid = pos["tr_value"] / pos["size"]  # ohne aktuellen Kurs: Bewertung von TR beim letzten Abgleich
            counts_as = S.resolve_isin(isin, PILLARS, extras)
            claim: list[str] = []
            if counts_as:
                claim = [k for k, p in pillars.items() if counts_as in _candidates(p["cfg"])
                         and counts_as in (p["st"].get("target"), p["st"].get("prev_target"))]
                if not claim:
                    claim = [k for k, p in pillars.items() if p["cfg"]["isin"] == counts_as]
                if not claim:
                    claim = [k for k, p in pillars.items() if counts_as in _candidates(p["cfg"])]
            if not claim:
                m = self.state["market"].get(isin, {})
                suggestion = S.suggest_pillar(self._name(isin), m.get("tags"))
                unassigned.append({
                    "isin": isin,
                    "name": self._name(isin),
                    "size": pos["size"],
                    "bid": bid,
                    "value": pos["size"] * bid if bid else None,
                    "suggestion": suggestion,
                    "suggestion_name": next((c["name"] for c in PILLARS if c["key"] == suggestion), None),
                })
                continue
            total = sum(amounts[k] for k in claim) or 1
            for k in claim:
                share = amounts[k] / total
                size = pos["size"] * share
                out[k].append({
                    "isin": isin,
                    "name": self._name(isin),
                    "counts_as": counts_as,
                    "counts_as_name": self._name(counts_as) if counts_as != isin else None,
                    "size": size,
                    "share": share,
                    "avg_buy": pos.get("avg_buy"),
                    "cost": size * pos["avg_buy"] if pos.get("avg_buy") else None,
                    "bid": bid,
                    "value": size * bid if bid else None,
                    "since": (self.state.get("held_since", {}).get(isin) or {}).get("date"),
                    "since_manual": (self.state.get("held_since", {}).get(isin) or {}).get("manual", False),
                    "change_24h": (quote["last"] / quote["pre"] - 1
                                   if (quote := self._price(isin)).get("last") and quote.get("pre") else None),
                })
        return out, unassigned

    @staticmethod
    def _reconcile(depot: dict, holdings: dict, unassigned: list[dict]) -> dict | None:
        """Abgleich mit Trade Republic: was TR zeigt und was davon in den Säulen zählt."""
        if not depot.get("connected"):
            return None
        tr_values = [p.get("tr_value") for p in (depot.get("positions") or {}).values()]
        counted = sum(h.get("value") or 0 for hs in holdings.values() for h in hs if not h.get("physical"))
        missing_price = [u["isin"] for u in unassigned if u.get("value") is None] + \
            [h["isin"] for hs in holdings.values() for h in hs if h.get("value") is None]
        return {
            "tr_positions": round(sum(tr_values), 2) if tr_values and all(v is not None for v in tr_values) else None,
            "cash": depot.get("cash"),
            "counted": round(counted, 2),
            "unassigned": round(sum(u.get("value") or 0 for u in unassigned), 2),
            "missing_price": missing_price,
        }

    def _paper_holdings(self, pillars: dict) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for key, p in pillars.items():
            paper = p["st"].get("paper")
            if not paper or not paper.get("isin"):
                out[key] = []
                continue
            bid = self._price(paper["isin"]).get("bid")
            out[key] = [{
                "isin": paper["isin"],
                "name": self._name(paper["isin"]),
                "size": paper["qty"],
                "avg_buy": paper["entry"],
                "cost": paper["invested"],
                "bid": bid,
                "value": paper["qty"] * bid if bid else None,
                "since": paper.get("since"),
                "change_24h": (q["last"] / q["pre"] - 1
                               if (q := self._price(paper["isin"])).get("last") and q.get("pre") else None),
            }]
        return out

    def _paper_execute(self, key: str, st: dict, amount: float, now: datetime) -> None:
        """Papiermodus: Market-Order mit 1 € Gebühr, Wechsel = Verkauf + Kauf."""
        if not st.get("month"):
            return
        target = st.get("target")
        paper = st.get("paper") or {}
        if paper.get("isin") == target:
            return
        if paper.get("isin"):
            bid = self._price(paper["isin"]).get("bid")
            if not bid:
                return
            proceeds = paper["qty"] * bid - ORDER_FEE
            st.setdefault("trades", []).append({"time": now.isoformat(), "side": "sell", "isin": paper["isin"],
                                                "qty": paper["qty"], "price": bid, "amount": proceeds})
            st["proceeds"] = proceeds
            st["paper"] = {}
        if target:
            ask = self._price(target).get("ask")
            if not ask:
                return
            budget = st.get("proceeds") if st.get("proceeds") else amount
            if budget < 2 * ORDER_FEE:
                return  # nichts zu kaufen (z. B. Gold-Säule durch physisches Gold gedeckt)
            qty = (budget - ORDER_FEE) / ask
            st["paper"] = {"isin": target, "qty": qty, "entry": ask, "invested": budget, "since": now.isoformat()}
            st.setdefault("trades", []).append({"time": now.isoformat(), "side": "buy", "isin": target,
                                                "qty": qty, "price": ask, "amount": budget})
            st["proceeds"] = None
        st["trades"] = st.get("trades", [])[-20:]

    # --------------------------------------------------------- Erkenntnisse

    def _instruction(self, p: dict, paper: bool) -> str:
        action = p["action"]
        if paper and action in ("hold", "cash"):
            if p["prev_target"] != p["target"]:
                return f"Papierdepot: {p['prev_target_name']} → {p['target_name'] or 'Cash'}"
            return f"Papierdepot hält {p['target_name'] or 'Cash'}"
        held = [h for h in p["held"] if not h.get("physical")]
        held_txt = ", ".join(f"{h['name']} ({h['isin']})" for h in held) or "–"
        held_val = sum(h.get("value") or 0 for h in held)
        tgt = f"{p['target_name']} ({p['target']})" if p["target"] else "Cash"
        phys = (f" – physisches Gold (≈ {S.fmt_eur(p['physical_value'], 0)}) bleibt liegen"
                if p.get("physical_value") else "")
        if action == "buy":
            budget = p.get("buy_budget")
            budget = budget if budget is not None else (p.get("proceeds") or p["amount"])
            covered = (f" (physisches Gold ≈ {S.fmt_eur(p['physical_value'], 0)} schon abgezogen)"
                       if p.get("physical_value") else "")
            return f"KAUFEN: {tgt} für ca. {S.fmt_eur(budget, 0)}{covered}"
        if action == "sell":
            return (f"KOMPLETT VERKAUFEN: {held_txt} (≈ {S.fmt_eur(held_val, 0)}), auch mit Verlust – "
                    f"Geld bleibt in Cash{phys}")
        if action == "switch":
            return (f"WECHSELN: {held_txt} komplett verkaufen (≈ {S.fmt_eur(held_val, 0)}), "
                    f"danach den Erlös in {tgt} anlegen{phys}")
        if action == "hold":
            return f"halten ({p['target_name']})"
        return "nichts tun – bleibt in Cash"

    def _reason(self, p: dict) -> str:
        sig = {r["key"]: r for r in p["signals"]}
        parts = []
        if "sma" in sig:
            parts.append(f"Kurs vs. Ø: {sig['sma']['value'].split('(')[-1].rstrip(')')}")
        if "mom" in sig:
            parts.append(f"12M-Rendite {sig['mom']['value']}")
        trend = "Trend aufwärts" if p["trend_on"] else "Trend abwärts"
        txt = f"{trend} ({'; '.join(parts)})" if parts else trend
        if p.get("reason"):
            txt += f" – {p['reason']}"
        return txt

    def _findings(self, now: datetime, data: dict) -> list[tuple[str, str, str | None]]:
        """Liefert (Schlüssel, Fingerprint, Text oder None). Text None = nur merken, nicht melden."""
        opts = self.options
        out: list[tuple[str, str, str | None]] = []
        paper = data["mode"] == "paper"
        pillars = data["pillars"]
        events = {(e["key"]): e for e in data["events"] if e["type"] == "decision"}

        # Monatsentscheidung
        if events:
            month = next(iter(pillars.values()))["decision_month"]
            lines = []
            changed = any(e["changed"] for e in events.values())
            for key, p in pillars.items():
                if key not in events:
                    continue
                emoji = EMOJI.get(p["state"], "•")
                line = f"{emoji} *{p['name']}*: {p['state_label']} – {self._reason(p)}"
                if p["action"] in ("buy", "sell", "switch") or events[key]["changed"]:
                    line += f"\n   ➜ {self._instruction(p, paper)}"
                lines.append(line)
            if changed or opts.get(CONF_MONTHLY_REPORT, True):
                head = f"📅 *Monatsentscheidung {S.month_label(month)}*"
                if not changed:
                    head += " – keine Änderung"
                out.append((f"decision:{month}", month, head + "\n" + "\n".join(lines)))

        # Handlungsbedarf im echten Depot
        if data["mode"] == "depot" and data["depot"]["connected"]:
            for key, p in pillars.items():
                if not p["action"]:
                    continue
                fp = f"{p['action']}:{p['target']}:{p['decision_month']}"
                k = f"action:{key}"
                if p["action"] in ("buy", "sell", "switch"):
                    text = None if key in events else \
                        f"🛠 *{p['name']}*: Depot weicht vom Ziel ab\n   ➜ {self._instruction(p, False)}"
                    out.append((k, fp, text))
                else:
                    prev = self.state["sent"].get(k, "")
                    done = prev.split(":")[0] in ("buy", "sell", "switch")
                    out.append((k, fp, f"✅ *{p['name']}*: umgesetzt – {p['status']}" if done else None))

        # Positionen, die keiner Säule zugeordnet werden konnten (einmal je ISIN)
        if data["mode"] == "depot" and data["depot"]["connected"]:
            for u in data["depot"].get("unassigned") or []:
                hint = (f" Vermutlich {u['suggestion_name']} – in den Optionen unter „Weitere ISINs {u['suggestion_name']}“ "
                        f"eintragen, dann zählt sie zur Säule." if u.get("suggestion_name")
                        else " Sie zählt zu keiner Säule.")
                out.append((f"unassigned:{u['isin']}", "1",
                            f"🔎 Depotposition nicht zugeordnet: {u['name']} ({u['isin']}), "
                            f"≈ {S.fmt_eur(u.get('value'), 0)}.{hint}"))

        # Rezessionszeichen
        for key, row in data["macro"].items():
            if row["state"] not in ("ok", "warn"):
                continue
            text = (f"⚠️ *{row['title']}* warnt jetzt: {row['value']}\n"
                    f"   Entscheidet nur, wenn der Welt-Trend kippt." if row["state"] == "warn"
                    else f"✔️ *{row['title']}* wieder ruhig: {row['value']}")
            out.append((f"recession:{key}", row["state"], text))

        # Umschaltkurs: würde das Signal zum Monatsende kippen?
        if opts.get(CONF_SWITCH_WARNING, True):
            today = now.date()
            days_left = (S.next_check_date(today) - today).days
            for key, p in pillars.items():
                if not p["switch"] or p["trend_on"] is None:
                    continue
                flip = p["would_flip"] and days_left <= 7
                fp = f"{S.month_key(today)}:{'flip' if flip else 'no'}"
                if flip:
                    word = "unter" if p["trend_on"] else "über"
                    new = "abwärts" if p["trend_on"] else "aufwärts"
                    text = (f"👀 *{p['name']}*: Trend würde zum Monatsende kippen ({new}).\n"
                            f"   Heute {S.fmt_eur(p['price'])} liegt {word} dem Umschaltkurs "
                            f"{S.fmt_eur(p['switch'])}. Entscheidung am {_date_de(S.next_check_date(today))}.")
                else:
                    text = None
                out.append((f"flip:{key}", fp, text))

        # Säulen-Abweichung
        ov = data["overview"]
        if data["mode"] == "depot" and data["depot"]["connected"] or data["mode"] == "paper":
            if ov["due"]:
                rows = "\n".join(f"   {r['name']}: {S.fmt_eur(r['value'], 0)} → {S.fmt_eur(r['target_value'], 0)} "
                                 f"({S.fmt_num(r['ist'] * 100, 0)} % / {S.fmt_num(r['soll'] * 100, 0)} %)"
                                 for r in ov["rows"])
                text = (f"⚖️ *Angleichen fällig*: um {S.fmt_num(ov['drift_pp'])} Pp von 40/30/30 abgewichen.\n"
                        f"{rows}\n   ➜ Beträge nach dem Pfeil wiederherstellen (Button „Angleichung übernehmen“).")
                out.append(("drift", "due", text))
            else:
                out.append(("drift", "ok", None))

            # Jährliches Angleichen
            rb_month = int(opts.get(CONF_REBALANCE_MONTH, DEFAULT_REBALANCE_MONTH))
            if now.month == rb_month and all(p["decision_month"] == S.month_key(now.date()) for p in pillars.values()):
                rows = "\n".join(f"   {r['name']}: {S.fmt_eur(r['value'], 0)} → {S.fmt_eur(r['target_value'], 0)}"
                                 for r in ov["rows"])
                out.append((f"annual:{now.year}", "1",
                            f"🗓 *Jährliches Angleichen {now.year}*\n{rows}\n"
                            f"   ➜ Auf 40/30/30 zurücksetzen (Button „Angleichung übernehmen“)."))

        # Login
        auth_fp = "expired" if data["depot"]["error"] == "auth" else "ok"
        if self.options.get(CONF_USE_DEPOT, True):
            out.append(("auth", auth_fp,
                        "🔑 Trade-Republic-Login abgelaufen – bitte in der Säulenwächter-App "
                        "(Seitenleiste in Home Assistant) neu anmelden."
                        if auth_fp == "expired" else None))
        return out

    async def _notify(self, now: datetime, data: dict) -> None:
        sent = self.state["sent"]
        findings = self._findings(now, data)
        first_run = not self.state.get("initialized")
        messages = []
        for key, fp, text in findings:
            if sent.get(key) == fp:
                continue
            is_new_key = key not in sent
            sent[key] = fp
            if text and not (first_run and not key.startswith("decision")) and not (
                    is_new_key and key.startswith("recession:")):
                messages.append(text)
        if first_run:
            messages.insert(0, f"🏛️ *{NAME}* ist aktiv. Modus: "
                               f"{'echtes Depot' if data['mode'] == 'depot' else 'Papierdepot'}.\n"
                               + "\n".join(f"{EMOJI.get(p['state'], '•')} {p['name']}: {p['status']}"
                                           for p in data["pillars"].values())
                               + "".join(f"\n🔎 Nicht zugeordnet: {u['name']} ({u['isin']})"
                                         + (f" – vermutlich {u['suggestion_name']}" if u.get("suggestion_name") else "")
                                         for u in (data["depot"].get("unassigned") or [])))
            self.state["initialized"] = True
        if messages:
            await self.send_message("\n\n".join(messages))

    async def send_message(self, body: str, force: bool = False) -> bool:
        opts = self.options
        if not (force or opts.get(CONF_NOTIFY, True)):
            return False
        phone, apikey = opts.get(CONF_WA_PHONE), opts.get(CONF_WA_APIKEY)
        service = (opts.get(CONF_HA_SERVICE) or "").strip()
        if not (phone and apikey) and not service:
            _LOGGER.info("Keine Benachrichtigung eingerichtet – Nachricht verworfen:\n%s", body)
            return False
        text = body if body.startswith("🏛️") else f"🏛️ *{NAME}*\n\n{body}"
        self.state.setdefault("log", []).append({"time": self.now().isoformat(), "text": text})
        self.state["log"] = self.state["log"][-30:]
        results = []
        if service:  # z. B. WhatsApp über ha-whatsapp, die Home-Assistant-App oder Telegram
            results.append(await send_ha_service(self._http, service, opts.get(CONF_HA_TARGET), text))
        if phone and apikey:
            results.append(await send_whatsapp(self._http, phone, apikey, text))
        return any(results)

    # ------------------------------------------------------------ Aktionen

    async def set_held_since(self, isin: str, day: str | None) -> None:
        """Kaufdatum einer Depotposition von Hand setzen (Trade Republic liefert keins)."""
        since = self.state.setdefault("held_since", {})
        if isin not in ((self.snapshot or {}).get("positions") or {}):
            raise ValueError("Position nicht im Depot")
        if day:
            parsed = date.fromisoformat(day)
            if parsed > self.now().date():
                raise ValueError("Datum liegt in der Zukunft")
            since[isin] = {"date": parsed.isoformat(), "manual": True}
        else:
            since.pop(isin, None)
        await self.async_save()
        await self.refresh()

    async def apply_rebalance(self) -> None:
        """Papierdepot: teilt das Papierkapital neu auf (Soll % · Σ Werte).

        Im echten Depot ohne Wirkung – dort gilt immer 40/30/30 vom tatsächlichen Depotwert, angeglichen wird bei
        Trade Republic.
        """
        if not self.data or self.data.get("mode") != "paper":
            return
        amounts = {r["key"]: round(r["target_value"], 2) for r in self.data["overview"]["rows"]}
        async with self._lock:
            self.set_amounts(amounts)
            # Papierdepot: angleichen heißt neu aufteilen
            if self.data["mode"] == "paper":
                for key, st in self.state["pillars"].items():
                    paper = st.get("paper")
                    if paper and paper.get("isin"):
                        paper["qty"] *= amounts[key] / max(self.data["pillars"][key]["value"], 1e-9)
                        paper["invested"] = amounts[key]
            self.state["sent"].pop("drift", None)
            await self.async_save()
        await self.async_request_refresh()
