"""Benachrichtigungen über einen Dienst in Home Assistant, z. B. WhatsApp über „ha-whatsapp“ (FaserF)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

import aiohttp

_LOGGER = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor/core/api"
MIN_GAP_S = 1.0  # höchstens etwa eine Nachricht pro Sekunde – sonst droht eine Sperre des WhatsApp-Kontos
_last_sent = 0.0
_lock = asyncio.Lock()


def normalize_target(target: str | None) -> str | None:
    """Telefonnummer ins internationale Format (+49…); Gruppen-IDs (…@g.us) und Chat-IDs bleiben unverändert."""
    if not target:
        return None
    t = target.strip()
    if "@" in t or not re.fullmatch(r"[+\d\s()/-]+", t):
        return t
    digits = re.sub(r"[^\d+]", "", t)
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("+"):
        return digits
    if digits.startswith("0"):
        return "+49" + digits[1:]
    return "+" + digits


async def send_ha_service(session: aiohttp.ClientSession, service: str, target: str | None, text: str,
                          token: str | None = None, url: str = SUPERVISOR_URL) -> bool:
    """Ruft einen Dienst in Home Assistant auf, z. B. „whatsapp.send_message“ (ha-whatsapp),
    „notify.mobile_app_handy“ (Home-Assistant-App) oder „telegram_bot.send_message“.

    Als App läuft der Aufruf über den Supervisor – ohne HA-URL und ohne eigenen Token."""
    global _last_sent
    token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN")
    service = (service or "").strip()
    if not token or "." not in service:
        return False
    domain, name = service.split(".", 1)
    data: dict = {"message": text}
    target = normalize_target(target)
    if target:
        # notify-Dienste erwarten eine Liste, andere (whatsapp, telegram) einen einzelnen Wert
        data["target"] = [target] if domain == "notify" else target
    if domain == "notify" and name.startswith("mobile_app"):
        data["title"] = "Säulenwächter"
    async with _lock:
        wait = MIN_GAP_S - (time.monotonic() - _last_sent)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with session.post(f"{url.rstrip('/')}/services/{domain}/{name}", json=data,
                                    headers={"Authorization": f"Bearer {token}"},
                                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status >= 300:
                    _LOGGER.warning("Dienst %s abgelehnt (HTTP %s): %s", service, resp.status,
                                    (await resp.text())[:200])
                    return False
                return True
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Dienst %s nicht erreichbar: %s", service, err)
            return False
        finally:
            _last_sent = time.monotonic()
