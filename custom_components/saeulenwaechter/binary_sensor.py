"""Binäre Sensoren: Trend je Säule, Rezessionszeichen, Angleichung fällig, TR-Verbindung."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PILLARS
from .entity import SaeulenEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []
    for pillar in PILLARS:
        entities.append(TrendSensor(coord, pillar))
        entities.append(FlipSensor(coord, pillar))
    for key, name in (("unemployment", "US-Arbeitslosenquote"), ("claims", "US-Erstanträge"),
                      ("yield_curve", "US-Zinskurve")):
        entities.append(RecessionSensor(coord, key, name))
    entities.append(RebalanceSensor(coord))
    entities.append(ConnectionSensor(coord))
    async_add_entities(entities)


class TrendSensor(SaeulenEntity, BinarySensorEntity):
    _attr_name = "Trend"
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator, pillar: dict) -> None:
        super().__init__(coordinator, "trend", pillar)
        self.entity_id = f"binary_sensor.{DOMAIN}_{pillar['key']}_trend"

    @property
    def is_on(self) -> bool | None:
        return self.pdata.get("trend_on")


class FlipSensor(SaeulenEntity, BinarySensorEntity):
    """An, wenn das Signal kippen würde, schlösse der Monat zum heutigen Kurs."""

    _attr_name = "Würde kippen"
    _attr_icon = "mdi:swap-vertical-bold"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, pillar: dict) -> None:
        super().__init__(coordinator, "would_flip", pillar)
        self.entity_id = f"binary_sensor.{DOMAIN}_{pillar['key']}_wuerde_kippen"

    @property
    def is_on(self) -> bool | None:
        return self.pdata.get("would_flip")


class RecessionSensor(SaeulenEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-decagram"

    def __init__(self, coordinator, key: str, name: str) -> None:
        super().__init__(coordinator, f"recession_{key}")
        self._key = key
        self._attr_name = f"Rezessionszeichen {name}"
        self.entity_id = f"binary_sensor.{DOMAIN}_rezession_{key}"

    @property
    def _row(self) -> dict:
        return ((self.coordinator.data or {}).get("macro") or {}).get(self._key) or {}

    @property
    def available(self) -> bool:
        return super().available and self._row.get("state") in ("ok", "warn")

    @property
    def is_on(self) -> bool | None:
        return self._row.get("state") == "warn"

    @property
    def extra_state_attributes(self) -> dict:
        return {"wert": self._row.get("value")}


class RebalanceSensor(SaeulenEntity, BinarySensorEntity):
    _attr_name = "Angleichung fällig"
    _attr_icon = "mdi:scale-balance"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rebalance_due")
        self.entity_id = f"binary_sensor.{DOMAIN}_angleichung_faellig"

    @property
    def is_on(self) -> bool | None:
        d = self.coordinator.data
        return d["overview"]["due"] if d else None

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.coordinator.data
        if not d:
            return None
        return {r["key"]: {"wert": round(r["value"], 2), "angeglichen": round(r["target_value"], 2)}
                for r in d["overview"]["rows"]}


class ConnectionSensor(SaeulenEntity, BinarySensorEntity):
    _attr_name = "Trade Republic verbunden"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "tr_connected")
        self.entity_id = f"binary_sensor.{DOMAIN}_trade_republic"

    @property
    def is_on(self) -> bool | None:
        d = self.coordinator.data
        return d["depot"]["connected"] if d else None

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.coordinator.data
        return {"fehler": d["depot"]["error"]} if d else None
