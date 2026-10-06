"""Sensoren: Zustand, Wert, Anteile, Umschaltkurs je Säule sowie Depot-Übersicht."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PILLARS, STATE_LABELS
from .entity import SaeulenEntity


@dataclass(frozen=True, kw_only=True)
class SaeulenSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict, dict], Any]
    attrs_fn: Callable[[dict, dict], dict] | None = None


def _pct(v: float | None) -> float | None:
    return round(v * 100, 2) if v is not None else None


def _round(v: float | None, d: int = 2) -> float | None:
    return round(v, d) if v is not None else None


PILLAR_SENSORS: list[SaeulenSensorDescription] = [
    SaeulenSensorDescription(
        key="zustand", name="Zustand", icon="mdi:pillar",
        device_class=SensorDeviceClass.ENUM,
        options=[v for v in STATE_LABELS.values()] + ["Unbekannt"],
        value_fn=lambda p, d: STATE_LABELS.get(p.get("state"), "Unbekannt"),
        attrs_fn=lambda p, d: {
            "status": p.get("status"),
            "entscheidung_monat": p.get("decision_month"),
            "trend": p.get("trend_on"),
            "ziel_isin": p.get("target"),
            "ziel_name": p.get("target_name"),
            "grund": p.get("reason"),
            "instrument": p.get("instrument"),
            "isin": p.get("isin"),
            "signale": [{k: r.get(k) for k in ("key", "state", "title", "value", "hint")}
                        for r in p.get("signals", [])],
            "historie": p.get("history", []),
            "naechste_pruefung": d.get("next_check"),
        },
    ),
    SaeulenSensorDescription(
        key="aktion", name="Aktion", icon="mdi:swap-horizontal-bold",
        value_fn=lambda p, d: p.get("action_label") or "–",
        attrs_fn=lambda p, d: {"aktion": p.get("action"), "bestand": p.get("held", []),
                               "ziel_isin": p.get("target"), "ziel_name": p.get("target_name")},
    ),
    SaeulenSensorDescription(
        key="wert", name="Wert", icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL, suggested_display_precision=0,
        value_fn=lambda p, d: _round(p.get("value")),
        attrs_fn=lambda p, d: {"betrag": p.get("amount"), "gemerkter_erloes": p.get("proceeds"),
                               "angeglichen": _round(p.get("target_value"))},
    ),
    SaeulenSensorDescription(
        key="ist_anteil", name="Ist-Anteil", icon="mdi:chart-pie",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda p, d: _pct(p.get("ist")),
        attrs_fn=lambda p, d: {"soll": _pct(p.get("soll")), "abweichung_pp": _round(p.get("diff_pp"))},
    ),
    SaeulenSensorDescription(
        key="umschaltkurs", name="Umschaltkurs", icon="mdi:arrow-decision",
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda p, d: _round(p.get("switch"), 4),
        attrs_fn=lambda p, d: {
            "richtung": "aus unter" if p.get("switch_dir") == "off" else "an über",
            "kurs_heute": p.get("price"),
            "abstand_pct": _pct(p["switch"] / p["price"] - 1) if p.get("switch") and p.get("price") else None,
            "wuerde_kippen": p.get("would_flip"),
        },
    ),
    SaeulenSensorDescription(
        key="kurs", name="Kurs", icon="mdi:chart-line",
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda p, d: p.get("price"),
        attrs_fn=lambda p, d: {"isin": p.get("isin"), "instrument": p.get("instrument"),
                               "aenderung_24h_pct": _pct(p.get("change_24h")),
                               "monatsschluss": p.get("close"), "monat": p.get("close_month")},
    ),
]


def _next_check(d: dict) -> datetime | None:
    if not d.get("next_check"):
        return None
    day = datetime.fromisoformat(d["next_check"]).date()
    return datetime.combine(day, time(7, 30), tzinfo=dt_util.get_time_zone("Europe/Berlin"))


GLOBAL_SENSORS: list[SaeulenSensorDescription] = [
    SaeulenSensorDescription(
        key="depotwert", name="Depotwert", icon="mdi:bank",
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL, suggested_display_precision=0,
        value_fn=lambda p, d: _round(d["overview"]["total"]),
        attrs_fn=lambda p, d: {"modus": d.get("mode"), "cash": d["depot"].get("cash"),
                               "saeulen": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                                           for r in d["overview"]["rows"]]},
    ),
    SaeulenSensorDescription(
        key="drift", name="Abweichung", icon="mdi:scale-unbalanced",
        native_unit_of_measurement="Pp", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda p, d: _round(d["overview"]["drift_pp"]),
    ),
    SaeulenSensorDescription(
        key="naechste_pruefung", name="Nächste Prüfung", icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda p, d: _next_check(d),
    ),
    SaeulenSensorDescription(
        key="euro_zins", name="Euro-Zins (12 Monate)", icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE, suggested_display_precision=2,
        value_fn=lambda p, d: _pct(next((x.get("hurdle") for x in d["pillars"].values()
                                         if x.get("hurdle") is not None), None)),
        attrs_fn=lambda p, d: {"quelle": next((x.get("hurdle_source") for x in d["pillars"].values()
                                               if x.get("hurdle_source")), None)},
    ),
    SaeulenSensorDescription(
        key="dollar", name="Dollar-Signal", icon="mdi:currency-usd",
        value_fn=lambda p, d: {True: "gesichert", False: "ungesichert"}.get(d["dollar"].get("hedge"), "unbekannt"),
        attrs_fn=lambda p, d: {"wert": d["dollar"].get("value")},
    ),
    SaeulenSensorDescription(
        key="modus", name="Modus", icon="mdi:briefcase-account",
        value_fn=lambda p, d: "Echtes Depot" if d.get("mode") == "depot" else "Papierdepot",
        attrs_fn=lambda p, d: {"tr_verbunden": d["depot"].get("connected"), "fehler": d["depot"].get("error"),
                               "positionen": d["depot"].get("positions"),
                               "nicht_zugeordnet": d["depot"].get("unassigned"),
                               "tr_verteilung": d.get("tr_split"),
                               "kursdaten_fehler": d.get("market_error"),
                               "wirtschaftsdaten": d.get("macro_status")},
    ),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    # Erst das Depot-Gerät, dann die Säulen (die über das Depot-Gerät hängen)
    entities: list[SensorEntity] = [SaeulenSensor(coord, desc, None) for desc in GLOBAL_SENSORS]
    for pillar in PILLARS:
        entities.extend(SaeulenSensor(coord, desc, pillar) for desc in PILLAR_SENSORS)
    async_add_entities(entities)


class SaeulenSensor(SaeulenEntity, SensorEntity):
    entity_description: SaeulenSensorDescription
    # Große Listen nicht in die Recorder-Datenbank schreiben
    _unrecorded_attributes = frozenset({"signale", "historie", "bestand", "positionen", "wirtschaftsdaten",
                                        "saeulen"})

    def __init__(self, coordinator, description: SaeulenSensorDescription, pillar: dict | None) -> None:
        super().__init__(coordinator, description.key, pillar)
        self.entity_description = description
        self.entity_id = f"sensor.{DOMAIN}_{pillar['key'] + '_' if pillar else ''}{description.key}"

    @property
    def native_value(self) -> Any:
        d = self.coordinator.data
        if not d:
            return None
        try:
            return self.entity_description.value_fn(self.pdata, d)
        except (KeyError, TypeError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.coordinator.data
        if not d or not self.entity_description.attrs_fn:
            return None
        try:
            return self.entity_description.attrs_fn(self.pdata, d)
        except (KeyError, TypeError, ZeroDivisionError):
            return None
