"""Benachrichtigungen: WhatsApp über CallMeBot und/oder einen Dienst in Home Assistant."""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp

_LOGGER = logging.getLogger(__name__)

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
MAX_LEN = 900  # CallMeBot kürzt sehr lange Texte; längere Nachrichten werden geteilt
PAUSE_S = 4  # CallMeBot verlangt Abstand zwischen zwei Nachrichten


def _split(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    parts, current = [], ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= MAX_LEN:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(block) > MAX_LEN:
            parts.append(block[:MAX_LEN])
            block = block[MAX_LEN:]
        current = block
    if current:
        parts.append(current)
    return parts


async def send_whatsapp(session: aiohttp.ClientSession, phone: str, apikey: str, text: str) -> bool:
    """Sendet text (ggf. in mehreren Teilen). True, wenn alle Teile angenommen wurden."""
    phone = phone.strip().lstrip("+").replace(" ", "")
    ok = True
    parts = _split(text)
    for i, part in enumerate(parts):
        if i:
            await asyncio.sleep(PAUSE_S)
        try:
            async with session.get(CALLMEBOT_URL, params={"phone": phone, "text": part, "apikey": apikey},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                body = await resp.text()
                if resp.status != 200 or "error" in body.lower()[:500]:
                    _LOGGER.warning("CallMeBot hat die Nachricht nicht angenommen (HTTP %s): %s",
                                    resp.status, body[:200])
                    ok = False
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("CallMeBot nicht erreichbar: %s", err)
            ok = False
    return ok


SUPERVISOR_URL = "http://supervisor/core/api"


async def send_ha_service(session: aiohttp.ClientSession, service: str, target: str | None, text: str,
                          token: str | None = None, url: str = SUPERVISOR_URL) -> bool:
    """Ruft einen Dienst in Home Assistant auf, z. B. „whatsapp.send_message“ (ha-whatsapp),
    „notify.mobile_app_handy“ (Home-Assistant-App) oder „telegram_bot.send_message“."""
    token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN")
    service = (service or "").strip()
    if not token or "." not in service:
        return False
    domain, name = service.split(".", 1)
    data: dict = {"message": text}
    if target:
        target = target.strip()
        # notify-Dienste erwarten eine Liste, andere (whatsapp, telegram) einen einzelnen Wert
        data["target"] = [target] if domain == "notify" else target.lstrip("+").replace(" ", "")
    if domain == "notify":
        data["title"] = "Säulenwächter"
    try:
        async with session.post(f"{url.rstrip('/')}/services/{domain}/{name}", json=data,
                                headers={"Authorization": f"Bearer {token}"},
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status >= 300:
                _LOGGER.warning("Dienst %s abgelehnt (HTTP %s): %s", service, resp.status, (await resp.text())[:200])
                return False
            return True
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.warning("Dienst %s nicht erreichbar: %s", service, err)
        return False
