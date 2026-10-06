"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION
from .coordinator import SaeulenCoordinator


class SaeulenEntity(CoordinatorEntity[SaeulenCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SaeulenCoordinator, key: str, pillar: dict | None = None) -> None:
        super().__init__(coordinator)
        self.pillar_key = pillar["key"] if pillar else None
        uid_device = f"{coordinator.entry.entry_id}_{self.pillar_key or 'depot'}"
        self._attr_unique_id = f"{uid_device}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid_device)},
            name=f"{NAME} {pillar['name']}" if pillar else NAME,
            manufacturer=NAME,
            model="Monatlicher Trendfolger" if pillar else "3-Säulen-Strategie",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def pdata(self) -> dict:
        return (self.coordinator.data or {}).get("pillars", {}).get(self.pillar_key, {})
