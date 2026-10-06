"""Überträgt den Zustand als Entitäten an Home Assistant (Core-API über den Supervisor).

Die Entitäts-IDs sind dieselben wie bei der früheren Integration, damit Automationen und Dashboards weiterlaufen.
Über die REST-API gesetzte Zustände überleben keinen Neustart von Home Assistant; die App sendet sie deshalb
jede Minute erneut.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from .const import ENTITY_PREFIX as P
from .const import NAME, PILLARS, STATE_LABELS, TZ

_LOGGER = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor/core/api"


def _pct(v: float | None) -> float | None:
    return round(v * 100, 2) if v is not None else None


def _round(v: float | None, d: int = 2) -> float | None:
    return round(v, d) if v is not None else None


def _next_check(d: dict) -> str | None:
    if not d.get("next_check"):
        return None
    day = datetime.fromisoformat(d["next_check"]).date()
    return datetime.combine(day, time(7, 30), tzinfo=ZoneInfo(TZ)).isoformat()


def _money(name: str, icon: str) -> dict:
    return {"friendly_name": name, "icon": icon, "unit_of_measurement": "EUR", "device_class": "monetary"}


def _onoff(v: bool | None) -> str:
    return "unavailable" if v is None else ("on" if v else "off")


def build_states(d: dict) -> dict[str, dict[str, Any]]:
    """entity_id → {state, attributes} aus den Daten der Engine."""
    out: dict[str, dict[str, Any]] = {}

    def put(entity_id: str, state: Any, attrs: dict) -> None:
        out[entity_id] = {"state": "unknown" if state is None else state, "attributes": attrs}

    for cfg in PILLARS:
        k = cfg["key"]
        p = d["pillars"].get(k, {})
        n = f"{NAME} {cfg['name']}"
        put(f"sensor.{P}_{k}_zustand", STATE_LABELS.get(p.get("state"), "Unbekannt"), {
            "friendly_name": f"{n} Zustand", "icon": "mdi:pillar",
            "status": p.get("status"), "entscheidung_monat": p.get("decision_month"), "trend": p.get("trend_on"),
            "ziel_isin": p.get("target"), "ziel_name": p.get("target_name"), "grund": p.get("reason"),
            "instrument": p.get("instrument"), "isin": p.get("isin"),
            "signale": [{x: r.get(x) for x in ("key", "state", "title", "value", "hint")} for r in p.get("signals", [])],
            "historie": p.get("history", []), "naechste_pruefung": d.get("next_check")})
        put(f"sensor.{P}_{k}_aktion", p.get("action_label") or "–", {
            "friendly_name": f"{n} Aktion", "icon": "mdi:swap-horizontal-bold", "aktion": p.get("action"),
            "anweisung": p.get("instruction"), "bestand": p.get("held", []),
            "ziel_isin": p.get("target"), "ziel_name": p.get("target_name")})
        put(f"sensor.{P}_{k}_wert", _round(p.get("value")), {
            **_money(f"{n} Wert", "mdi:cash"), "state_class": "total",
            "betrag": p.get("amount"), "gemerkter_erloes": p.get("proceeds"), "angeglichen": _round(p.get("target_value")),
            "physisches_gold": _round(p.get("physical_value"))})
        put(f"sensor.{P}_{k}_ist_anteil", _pct(p.get("ist")), {
            "friendly_name": f"{n} Ist-Anteil", "icon": "mdi:chart-pie", "unit_of_measurement": "%",
            "state_class": "measurement", "soll": _pct(p.get("soll")), "abweichung_pp": _round(p.get("diff_pp"))})
        put(f"sensor.{P}_{k}_umschaltkurs", _round(p.get("switch"), 4), {
            **_money(f"{n} Umschaltkurs", "mdi:arrow-decision"),
            "richtung": "aus unter" if p.get("switch_dir") == "off" else "an über", "kurs_heute": p.get("price"),
            "abstand_pct": _pct(p["switch"] / p["price"] - 1) if p.get("switch") and p.get("price") else None,
            "wuerde_kippen": p.get("would_flip")})
        put(f"sensor.{P}_{k}_kurs", p.get("price"), {
            **_money(f"{n} Kurs", "mdi:chart-line"), "isin": p.get("isin"), "instrument": p.get("instrument"),
            "aenderung_24h_pct": _pct(p.get("change_24h")), "monatsschluss": p.get("close"), "monat": p.get("close_month")})
        put(f"binary_sensor.{P}_{k}_trend", _onoff(p.get("trend_on")),
            {"friendly_name": f"{n} Trend", "icon": "mdi:trending-up"})
        put(f"binary_sensor.{P}_{k}_wuerde_kippen", _onoff(p.get("would_flip")),
            {"friendly_name": f"{n} Würde kippen", "icon": "mdi:swap-vertical-bold", "device_class": "problem"})

    ov, st = d["overview"], d.get("stats") or {}
    total = st.get("total") or {}
    put(f"sensor.{P}_depotwert", _round(ov["total"]), {
        **_money(f"{NAME} Depotwert", "mdi:bank"), "state_class": "total", "modus": d.get("mode"),
        "cash": d["depot"].get("cash"),
        "saeulen": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in ov["rows"]],
        "statistik": st})
    pg = d.get("physical_gold") or {}
    put(f"sensor.{P}_physisches_gold", _round(pg.get("value")), {
        **_money(f"{NAME} Physisches Gold", "mdi:gold"), "state_class": "total",
        "feingold_g": _round(pg.get("fine_grams"), 3), "einstand": pg.get("cost"),
        "goldpreis_eur_g": _round(pg.get("price_g"), 3),
        "bestand": [{k: e.get(k) for k in ("name", "qty", "unit", "fineness", "fine_grams", "cost", "bought", "value")}
                    for e in pg.get("items", [])]})
    zins = st.get("interest") or {}
    put(f"sensor.{P}_zins", _pct(zins.get("rate")), {
        "friendly_name": f"{NAME} Zinsen auf Cash", "icon": "mdi:percent-circle", "unit_of_measurement": "%",
        "quelle": zins.get("source"), "stand": zins.get("at"), "cash": zins.get("cash"),
        "zinsen_pro_jahr": zins.get("per_year"), "gutgeschrieben": zins.get("earned")})
    put(f"sensor.{P}_gewinn_verlust", _round(total.get("pnl")), {
        **_money(f"{NAME} Gewinn/Verlust", "mdi:finance"), "prozent": _pct(total.get("pnl_pct")),
        "einstand": total.get("cost")})
    put(f"sensor.{P}_drift", _round(ov["drift_pp"]), {
        "friendly_name": f"{NAME} Abweichung", "icon": "mdi:scale-unbalanced", "unit_of_measurement": "Pp",
        "state_class": "measurement"})
    put(f"sensor.{P}_naechste_pruefung", _next_check(d), {
        "friendly_name": f"{NAME} Nächste Prüfung", "icon": "mdi:calendar-clock", "device_class": "timestamp"})
    hurdle = next((x for x in d["pillars"].values() if x.get("hurdle") is not None), {})
    put(f"sensor.{P}_euro_zins", _pct(hurdle.get("hurdle")), {
        "friendly_name": f"{NAME} Euro-Zins (12 Monate)", "icon": "mdi:percent", "unit_of_measurement": "%",
        "quelle": hurdle.get("hurdle_source")})
    put(f"sensor.{P}_dollar", {True: "gesichert", False: "ungesichert"}.get(d["dollar"].get("hedge"), "unbekannt"), {
        "friendly_name": f"{NAME} Dollar-Signal", "icon": "mdi:currency-usd", "wert": d["dollar"].get("value")})
    put(f"sensor.{P}_modus", "Echtes Depot" if d.get("mode") == "depot" else "Papierdepot", {
        "friendly_name": f"{NAME} Modus", "icon": "mdi:briefcase-account",
        "tr_verbunden": d["depot"].get("connected"), "fehler": d["depot"].get("error"),
        "positionen": d["depot"].get("positions"), "nicht_zugeordnet": d["depot"].get("unassigned"),
        "tr_verteilung": d.get("tr_split"), "kursdaten_fehler": d.get("market_error"),
        "wirtschaftsdaten": d.get("macro_status")})
    for key, name in (("unemployment", "US-Arbeitslosenquote"), ("claims", "US-Erstanträge"),
                      ("yield_curve", "US-Zinskurve")):
        row = (d.get("macro") or {}).get(key) or {}
        put(f"binary_sensor.{P}_rezession_{key}",
            {"warn": "on", "ok": "off"}.get(row.get("state"), "unavailable"),
            {"friendly_name": f"{NAME} Rezessionszeichen {name}", "icon": "mdi:alert-decagram",
             "device_class": "problem", "wert": row.get("value")})
    put(f"binary_sensor.{P}_angleichung_faellig", _onoff(ov["due"]), {
        "friendly_name": f"{NAME} Angleichung fällig", "icon": "mdi:scale-balance", "device_class": "problem",
        **{r["key"]: {"wert": round(r["value"], 2), "angeglichen": round(r["target_value"], 2)} for r in ov["rows"]}})
    put(f"binary_sensor.{P}_handlung_noetig", _onoff(bool(d.get("todo"))), {
        "friendly_name": f"{NAME} Handlung nötig", "icon": "mdi:alert-octagon", "device_class": "problem",
        "anweisungen": [t["text"] for t in d.get("todo") or []]})
    put(f"binary_sensor.{P}_trade_republic", _onoff(d["depot"].get("connected")), {
        "friendly_name": f"{NAME} Trade Republic verbunden", "device_class": "connectivity",
        "fehler": d["depot"].get("error")})
    return out


class HomeAssistantPublisher:
    """Schreibt die Zustände über die Supervisor-Proxy-API in Home Assistant."""

    def __init__(self, session: aiohttp.ClientSession, token: str | None = None, url: str = SUPERVISOR_URL) -> None:
        self._session = session
        self._token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN")
        self._url = url.rstrip("/")
        self._warned = False

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    async def publish(self, data: dict | None) -> int:
        """Sendet alle Zustände. Ergebnis: Anzahl erfolgreich gesetzter Entitäten."""
        if not self.enabled or not data:
            return 0
        ok = 0
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        for entity_id, body in build_states(data).items():
            try:
                async with self._session.post(f"{self._url}/states/{entity_id}", json=body, headers=headers,
                                              timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status < 300:
                        ok += 1
                    elif not self._warned:
                        _LOGGER.warning("Home Assistant lehnt %s ab (HTTP %s)", entity_id, resp.status)
                        self._warned = True
            except (aiohttp.ClientError, TimeoutError) as err:
                if not self._warned:
                    _LOGGER.warning("Home Assistant nicht erreichbar: %s", err)
                    self._warned = True
                break
        if ok:
            self._warned = False
        return ok
