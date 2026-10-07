"""Startpunkt der App: Engine, Weboberfläche (Ingress) und Übertragung an Home Assistant."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from pathlib import Path

import aiohttp
from aiohttp import web

from .const import NAME, UPDATE_INTERVAL_MIN, VERSION
from .engine import Engine
from .ha import HomeAssistantPublisher
from .web import INGRESS_IP, make_app

_LOGGER = logging.getLogger("saeulenwaechter")

DATA_DIR = Path(os.environ.get("SW_DATA_DIR", "/data"))
PORT = int(os.environ.get("SW_PORT", "8099"))
PUBLISH_EVERY_S = 60


def load_options(path: Path) -> dict:
    """Die Optionen, die der Nutzer in der App eingetragen hat (vom Supervisor nach /data/options.json geschrieben)."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        _LOGGER.warning("%s fehlt – Standardeinstellungen", path)
        return {}


async def main() -> None:
    logging.basicConfig(level=os.environ.get("SW_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    options = load_options(DATA_DIR / "options.json")
    async with aiohttp.ClientSession() as http, \
            aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as tr_session:
        engine = Engine(DATA_DIR, options, http, tr_session)
        await engine.async_load()
        engine.compute_cached()  # Oberfläche hat sofort Daten, frische Kurse folgen im ersten Durchlauf
        publisher = HomeAssistantPublisher(http)

        async def changed() -> None:
            await publisher.publish(engine.data)

        allowed = () if os.environ.get("SW_ALLOW_ALL") else (INGRESS_IP, "127.0.0.1", "::1")
        runner = web.AppRunner(make_app(engine, changed, allowed))
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        _LOGGER.info("%s %s läuft auf Port %s (Home Assistant: %s)", NAME, VERSION, PORT,
                     "verbunden" if publisher.enabled else "ohne Token")

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        async def updates() -> None:
            while not stop.is_set():
                await engine.refresh()
                await publisher.publish(engine.data)
                try:
                    await asyncio.wait_for(stop.wait(), UPDATE_INTERVAL_MIN * 60)
                except TimeoutError:
                    pass

        async def republish() -> None:
            # Über die REST-API gesetzte Zustände gehen bei einem Neustart von Home Assistant verloren
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), PUBLISH_EVERY_S)
                except TimeoutError:
                    await publisher.publish(engine.data)

        tasks = [asyncio.create_task(updates()), asyncio.create_task(republish())]
        await stop.wait()
        for t in tasks:
            t.cancel()
        await engine.async_save()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
