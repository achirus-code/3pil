"""Weboberfläche der App (Home-Assistant-Ingress): Übersicht, Aktionen und Trade-Republic-Login."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp
from aiohttp import web

from .engine import Engine
from .tr_api import TRAuthError, TRError

_LOGGER = logging.getLogger(__name__)

WWW = Path(__file__).parent / "www"
INGRESS_IP = "172.30.32.2"  # der Supervisor leitet Ingress-Anfragen nur von dieser Adresse weiter

ENGINE = web.AppKey("engine", Engine)
ON_CHANGE = web.AppKey("on_change", Callable[[], Awaitable[None]])


def make_app(engine: Engine, on_change: Callable[[], Awaitable[None]] | None = None,
             allowed: tuple[str, ...] = (INGRESS_IP,)) -> web.Application:
    @web.middleware
    async def only_ingress(request: web.Request, handler):
        if allowed and request.remote not in allowed and request.path != "/api/health":
            raise web.HTTPForbidden(text="Nur über Home Assistant erreichbar.")
        return await handler(request)

    async def nothing() -> None:
        return None

    app = web.Application(middlewares=[only_ingress])
    app[ENGINE] = engine
    app[ON_CHANGE] = on_change or nothing
    app.router.add_get("/", index)
    app.router.add_get("/saeulenwaechter-card.js", card)
    app.router.add_get("/api/data", data)
    app.router.add_post("/api/action", action)
    app.router.add_get("/api/login", login_status)
    app.router.add_post("/api/login/start", login_start)
    app.router.add_post("/api/login/complete", login_complete)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/health", health)
    return app


def _no_cache(resp: web.StreamResponse) -> web.StreamResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def index(request: web.Request) -> web.StreamResponse:
    return _no_cache(web.FileResponse(WWW / "index.html"))


async def card(request: web.Request) -> web.StreamResponse:
    return _no_cache(web.FileResponse(WWW / "saeulenwaechter-card.js"))


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def data(request: web.Request) -> web.Response:
    engine = request.app[ENGINE]
    if not engine.data:
        return web.json_response({"error": engine.last_error or "Säulenwächter hat noch keine Daten",
                                  "login": engine.login_status()}, status=503)
    out = {k: v for k, v in engine.data.items() if k != "events"}
    out["log"] = engine.state.get("log", [])[-10:]
    out["trades"] = {k: st.get("trades", [])[-10:] for k, st in engine.state["pillars"].items()}
    out["login"] = engine.login_status()
    out["last_error"] = engine.last_error
    return _no_cache(web.json_response(out))


async def _json(request: web.Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="JSON erwartet")
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="JSON-Objekt erwartet")
    return body


async def action(request: web.Request) -> web.Response:
    engine = request.app[ENGINE]
    act = (await _json(request)).get("action")
    if act == "refresh":
        await engine.refresh()
    elif act == "rebalance":
        await engine.apply_rebalance()
    elif act == "test":
        await engine.send_message("Testnachricht – die Verbindung steht. ✅", force=True)
        await engine.async_save()
    else:
        raise web.HTTPBadRequest(text="Unbekannte Aktion")
    await request.app[ON_CHANGE]()
    return web.json_response({"ok": True})


async def login_status(request: web.Request) -> web.Response:
    return _no_cache(web.json_response(request.app[ENGINE].login_status()))


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def login_start(request: web.Request) -> web.Response:
    body = await _json(request)
    phone, pin = str(body.get("phone") or "").strip(), str(body.get("pin") or "").strip()
    if not phone or not (pin.isdigit() and len(pin) == 4):
        return _error("Telefonnummer und 4-stellige PIN eingeben.")
    try:
        kind = await request.app[ENGINE].login_start(phone, pin)
    except TRError as err:
        return _error(str(err))
    except aiohttp.ClientError as err:
        return _error(f"Trade Republic nicht erreichbar: {err}", 502)
    return web.json_response({"kind": kind})


async def login_complete(request: web.Request) -> web.Response:
    body = await _json(request)
    try:
        await request.app[ENGINE].login_complete(code=body.get("code") or None)
    except TRAuthError:
        return _error("Noch nicht in der Trade-Republic-App bestätigt – bitte bestätigen und erneut absenden.", 409)
    except TRError as err:
        return _error(str(err))
    except aiohttp.ClientError as err:
        return _error(f"Trade Republic nicht erreichbar: {err}", 502)
    await request.app[ON_CHANGE]()
    return web.json_response({"ok": True})


async def logout(request: web.Request) -> web.Response:
    await request.app[ENGINE].logout()
    await request.app[ON_CHANGE]()
    return web.json_response({"ok": True})
