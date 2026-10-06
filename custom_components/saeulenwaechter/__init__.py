"""Säulenwächter – die 3-Säulen-Strategie (Welt 40 / Gold 30 / Anleihen 30) für Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, NAME, VERSION
from .coordinator import SaeulenCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
URL_BASE = f"/{DOMAIN}_static"
CARD_URL = f"{URL_BASE}/saeulenwaechter-card.js?v={VERSION}"
PANEL_PATH = DOMAIN
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(Path(__file__).parent / "frontend"), False)]
    )
    frontend.add_extra_js_url(hass, CARD_URL)
    websocket_api.async_register_command(hass, ws_data)
    websocket_api.async_register_command(hass, ws_action)

    async def _refresh(call: ServiceCall) -> None:
        for coord in hass.data[DOMAIN].values():
            await coord.async_request_refresh()

    async def _rebalance(call: ServiceCall) -> None:
        for coord in hass.data[DOMAIN].values():
            await coord.apply_rebalance()

    async def _test(call: ServiceCall) -> None:
        for coord in hass.data[DOMAIN].values():
            await coord.send_message(call.data.get("message") or "Testnachricht – die Verbindung steht. ✅",
                                     force=True)

    hass.services.async_register(DOMAIN, "refresh", _refresh)
    hass.services.async_register(DOMAIN, "apply_rebalance", _rebalance)
    hass.services.async_register(DOMAIN, "send_test_message", _test,
                                 schema=vol.Schema({vol.Optional("message"): str}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coord = SaeulenCoordinator(hass, entry)
    await coord.async_load()
    await coord.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coord
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))

    if PANEL_PATH not in hass.data.get("frontend_panels", {}):
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=NAME,
            sidebar_icon="mdi:pillar",
            frontend_url_path=PANEL_PATH,
            require_admin=False,
            config={"_panel_custom": {"name": "saeulenwaechter-panel", "module_url": CARD_URL,
                                      "embed_iframe": False, "trust_external": False}},
        )
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coord: SaeulenCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coord.async_save()
        if not hass.data[DOMAIN]:
            frontend.async_remove_panel(hass, PANEL_PATH)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    from homeassistant.helpers.storage import Store
    from .const import STORAGE_VERSION
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


def _coord(hass: HomeAssistant) -> SaeulenCoordinator | None:
    coords = list(hass.data.get(DOMAIN, {}).values())
    return coords[0] if coords else None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/data"})
@callback
def ws_data(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord = _coord(hass)
    if not coord or not coord.data:
        connection.send_error(msg["id"], "not_ready", "Säulenwächter hat noch keine Daten")
        return
    data = {k: v for k, v in coord.data.items() if k != "events"}
    data["log"] = coord.state.get("log", [])[-10:]
    data["trades"] = {k: st.get("trades", [])[-10:] for k, st in coord.state["pillars"].items()}
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/action",
    vol.Required("action"): vol.In(["refresh", "rebalance", "test"]),
})
@websocket_api.async_response
async def ws_action(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord = _coord(hass)
    if not coord:
        connection.send_error(msg["id"], "not_ready", "Säulenwächter ist nicht eingerichtet")
        return
    if msg["action"] == "refresh":
        await coord.async_request_refresh()
    elif msg["action"] == "rebalance":
        await coord.apply_rebalance()
    else:
        await coord.send_message("Testnachricht – die Verbindung steht. ✅", force=True)
    connection.send_result(msg["id"], {"ok": True})
