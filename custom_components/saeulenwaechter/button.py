"""Buttons: aktualisieren, Angleichung übernehmen, Testnachricht."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SaeulenEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SaeulenButton(coord, "aktualisieren", "Jetzt aktualisieren", "mdi:refresh"),
        SaeulenButton(coord, "angleichen", "Angleichung übernehmen", "mdi:scale-balance"),
        SaeulenButton(coord, "testnachricht", "WhatsApp-Testnachricht", "mdi:whatsapp"),
    ])


class SaeulenButton(SaeulenEntity, ButtonEntity):
    def __init__(self, coordinator, key: str, name: str, icon: str) -> None:
        super().__init__(coordinator, f"button_{key}")
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self.entity_id = f"button.{DOMAIN}_{key}"

    async def async_press(self) -> None:
        if self._key == "aktualisieren":
            await self.coordinator.async_request_refresh()
        elif self._key == "angleichen":
            await self.coordinator.apply_rebalance()
        else:
            await self.coordinator.send_message("Testnachricht – die Verbindung steht. ✅", force=True)
