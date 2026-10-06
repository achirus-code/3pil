"""Config-Flow: einmaliger Trade-Republic-Login und WhatsApp-Einrichtung."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BLS_KEY,
    CONF_COOKIES,
    CONF_DEVICE_ID,
    CONF_LOGIN_AT,
    CONF_MONTHLY_REPORT,
    CONF_NOTIFY,
    CONF_PHONE,
    CONF_PIN,
    CONF_REBALANCE_MONTH,
    CONF_SEC_ACC_NO,
    CONF_SWITCH_WARNING,
    CONF_TOTAL,
    CONF_USE_DEPOT,
    CONF_WA_APIKEY,
    CONF_WA_PHONE,
    DEFAULT_REBALANCE_MONTH,
    DEFAULT_TOTAL,
    DOMAIN,
    NAME,
)
from .tr_api import TRAuthError, TRError, TradeRepublic

_LOGGER = logging.getLogger(__name__)


def _normalize_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif phone.startswith("0"):
        phone = "+49" + phone[1:]
    elif not phone.startswith("+"):
        phone = "+" + phone
    return phone


def _notify_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_WA_PHONE, default=defaults.get(CONF_WA_PHONE, "")): str,
        vol.Optional(CONF_WA_APIKEY, default=defaults.get(CONF_WA_APIKEY, "")): str,
        vol.Required(CONF_TOTAL, default=defaults.get(CONF_TOTAL, DEFAULT_TOTAL)): vol.All(
            vol.Coerce(float), vol.Range(min=100)),
    })


class SaeulenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung des Säulenwächters."""

    VERSION = 1

    def __init__(self) -> None:
        self._tr: TradeRepublic | None = None
        self._phone: str | None = None
        self._login: dict[str, Any] = {}
        self._reauth_entry: ConfigEntry | None = None

    def _client(self) -> TradeRepublic:
        if self._tr is None:
            session = async_create_clientsession(self.hass, cookie_jar=aiohttp.DummyCookieJar())
            device_id = self._reauth_entry.data.get(CONF_DEVICE_ID) if self._reauth_entry else None
            self._tr = TradeRepublic(session, device_id=device_id)
        return self._tr

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_show_menu(step_id="user", menu_options=["login", "paper"])

    async def async_step_paper(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ohne Login: alle Signale + Papierdepot."""
        self._login = {CONF_USE_DEPOT: False}
        return await self.async_step_notify()

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            self._phone = _normalize_phone(user_input[CONF_PHONE])
            try:
                kind = await self._client().login_start(self._phone, user_input[CONF_PIN])
            except TRError as err:
                errors["base"] = "login_failed"
                placeholders["error"] = str(err)
            except aiohttp.ClientError as err:
                errors["base"] = "cannot_connect"
                placeholders["error"] = str(err)
            else:
                if kind == "AUTHENTICATOR_VERIFICATION":
                    return await self.async_step_code()
                return await self.async_step_confirm()
        default_phone = self._phone or (self._reauth_entry.data.get(CONF_PHONE) if self._reauth_entry else "")
        return self.async_show_form(
            step_id="login",
            data_schema=vol.Schema({
                vol.Required(CONF_PHONE, default=default_phone or ""): str,
                vol.Required(CONF_PIN): vol.All(str, vol.Length(min=4, max=4)),
            }),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                await self._client().login_complete(code=user_input["code"].strip())
                return await self._logged_in()
            except TRError as err:
                errors["base"] = "login_failed"
                placeholders["error"] = str(err)
        return self.async_show_form(step_id="code", data_schema=vol.Schema({vol.Required("code"): str}),
                                    errors=errors, description_placeholders=placeholders)

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                await self._client().login_complete(wait=25)
                return await self._logged_in()
            except TRAuthError:
                errors["base"] = "not_confirmed"
            except TRError as err:
                errors["base"] = "login_failed"
                placeholders["error"] = str(err)
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}),
                                    errors=errors, description_placeholders=placeholders)

    async def _logged_in(self) -> ConfigFlowResult:
        tr = self._client()
        self._login = {
            CONF_USE_DEPOT: True,
            CONF_PHONE: self._phone,
            CONF_COOKIES: dict(tr.cookies),
            CONF_DEVICE_ID: tr.device_id,
            CONF_SEC_ACC_NO: tr.sec_acc_no,
            CONF_LOGIN_AT: dt_util.utcnow().isoformat(),
        }
        if self._reauth_entry:
            return self.async_update_reload_and_abort(
                self._reauth_entry, data={**self._reauth_entry.data, **self._login})
        return await self.async_step_notify()

    async def async_step_notify(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = {**self._login, CONF_LOGIN_AT: self._login.get(CONF_LOGIN_AT, "paper")}
            options = {
                CONF_WA_PHONE: user_input.get(CONF_WA_PHONE, "").strip(),
                CONF_WA_APIKEY: user_input.get(CONF_WA_APIKEY, "").strip(),
                CONF_TOTAL: user_input[CONF_TOTAL],
                CONF_NOTIFY: True,
                CONF_MONTHLY_REPORT: True,
                CONF_SWITCH_WARNING: True,
                CONF_REBALANCE_MONTH: DEFAULT_REBALANCE_MONTH,
            }
            return self.async_create_entry(title=NAME, data=data, options=options)
        return self.async_show_form(step_id="notify", data_schema=_notify_schema({}))

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_login()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SaeulenOptionsFlow()


class SaeulenOptionsFlow(OptionsFlow):
    """Optionen: WhatsApp, Beträge, Meldungen."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        o = {**self.config_entry.options}
        has_login = bool(self.config_entry.data.get(CONF_COOKIES))
        schema: dict = {
            vol.Optional(CONF_WA_PHONE, default=o.get(CONF_WA_PHONE, "")): str,
            vol.Optional(CONF_WA_APIKEY, default=o.get(CONF_WA_APIKEY, "")): str,
            vol.Required(CONF_NOTIFY, default=o.get(CONF_NOTIFY, True)): bool,
            vol.Required(CONF_MONTHLY_REPORT, default=o.get(CONF_MONTHLY_REPORT, True)): bool,
            vol.Required(CONF_SWITCH_WARNING, default=o.get(CONF_SWITCH_WARNING, True)): bool,
            vol.Required(CONF_TOTAL, default=o.get(CONF_TOTAL, DEFAULT_TOTAL)): vol.All(
                vol.Coerce(float), vol.Range(min=100)),
            vol.Required(CONF_REBALANCE_MONTH, default=o.get(CONF_REBALANCE_MONTH, DEFAULT_REBALANCE_MONTH)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Optional(CONF_BLS_KEY, default=o.get(CONF_BLS_KEY, "")): str,
        }
        if has_login:
            schema[vol.Required(CONF_USE_DEPOT, default=o.get(CONF_USE_DEPOT, True))] = bool
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
