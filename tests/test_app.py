"""Die App ohne Home Assistant: Engine (Papier- und echtes Depot), Weboberfläche und Übertragung an HA.

Kurse und Wirtschaftsdaten kommen aus der aufgezeichneten Live-Datei tests/fixture_live.json.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aiohttp import web

from sw import engine as engine_mod
from sw import macro
from sw.engine import Engine
from sw.ha import HomeAssistantPublisher, build_states
from sw.tr_api import TRAuthError, TradeRepublic
from sw.web import make_app

FIXTURE = json.loads((Path(__file__).parent / "fixture_live.json").read_text())
BERLIN = ZoneInfo("Europe/Berlin")
OPTIONS = {"total": 100000, "ha_service": "whatsapp.send_message", "ha_target": "+4917000000", "notify": True,
           "monthly_report": True, "switch_warning": True, "rebalance_month": 1, "use_depot": True}


@pytest.fixture
def sent():
    return []


@pytest.fixture
def market(monkeypatch):
    """Kurse/Kerzen und Wirtschaftsdaten aus der Aufzeichnung; die Datei selbst bleibt unverändert."""
    data = json.loads(json.dumps(FIXTURE["market"]))

    async def market_data(self, isins, exchange, candles=True, names=True):
        out = {}
        for i in isins:
            d = data.get(i, {})
            out[i] = {"price": d.get("price")}
            if candles:
                out[i]["candles"] = d.get("candles")
            if names:
                out[i]["name"] = d.get("name")
        return out

    def fetcher(key):
        async def f(session, *a):
            if key == "ecb_rate":
                return {"2026-10-02": 2.0, "2026-10-05": 2.0}
            return FIXTURE["macro"][key]
        return f

    monkeypatch.setattr(TradeRepublic, "market_data", market_data)
    monkeypatch.setattr(macro, "FETCHERS", {k: fetcher(k) for k in macro.FETCHERS})
    monkeypatch.setattr(engine_mod, "FETCHERS", {k: fetcher(k) for k in macro.FETCHERS})
    return data


@pytest.fixture
async def make_engine(tmp_path, market, sent, monkeypatch):
    async def send(session, service, target, text):
        sent.append(text)
        return True

    monkeypatch.setattr(engine_mod, "send_ha_service", send)

    async def tr_logout(self):
        self.cookies = {}

    monkeypatch.setattr(TradeRepublic, "logout", tr_logout)

    async def no_trades(self, isins=None, max_pages=60):
        return []

    monkeypatch.setattr(TradeRepublic, "transactions", no_trades)  # kein Netz in den Tests
    sessions = []

    async def factory(options=None, when="2026-10-06 10:00"):
        http = aiohttp.ClientSession()
        sessions.append(http)
        eng = Engine(tmp_path, {**OPTIONS, **(options or {})}, http)
        await eng.async_load()
        eng.clock = datetime.fromisoformat(when).replace(tzinfo=BERLIN)
        eng.now = lambda: eng.clock
        return eng

    yield factory
    for s in sessions:
        await s.close()


# ------------------------------------------------------------------ Papierdepot

async def test_paper_decision_messages_and_state_file(make_engine, sent, tmp_path):
    eng = await make_engine()
    d = await eng.refresh()
    assert d["mode"] == "paper"
    states = {k: p["state"] for k, p in d["pillars"].items()}
    assert states == {"welt": "in", "gold": "in", "anleihen": "cash"}
    assert 99_000 < d["overview"]["total"] < 101_000
    assert d["pillars"]["welt"]["signals"][0]["title"] == "Entscheidung Okt. 2026"
    assert len(sent) == 1 and "Monatsentscheidung Okt. 2026" in sent[0]
    assert len(d["value_history"]) == 1
    # Bestandsbalken auch im Papierdepot: Welt und Gold investiert, Anleihen-Anteil als Cash
    split = d["tr_split"]
    assert split["source"] == "paper"
    rows = {r["key"]: r for r in split["rows"]}
    assert rows["welt"]["ist"] == pytest.approx(0.4, abs=0.01) and rows["anleihen"]["ist"] == 0
    assert split["cash"]["ist"] == pytest.approx(0.3, abs=0.01) and split["cash"]["soll"] == pytest.approx(0.3)

    await eng.refresh()
    assert len(sent) == 1  # nichts Neues

    # Zustand liegt in /data/state.json und überlebt einen Neustart
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["pillars"]["welt"]["month"] == "2026-10"
    eng2 = await make_engine(when="2026-11-02 10:00")
    await eng2.refresh()
    assert len(sent) == 2 and "Monatsentscheidung Nov. 2026" in sent[1]
    assert [h["month"] for h in eng2.data["pillars"]["welt"]["history"]] == ["2026-10", "2026-11"]


async def test_paper_cash_earns_interest(make_engine):
    eng = await make_engine({"cash_zins": "2,0"})
    d = await eng.refresh()
    assert d["stats"]["interest"]["rate"] == pytest.approx(0.02)
    assert d["stats"]["interest"]["source"] == "option"
    start = d["pillars"]["anleihen"]["value"]
    assert d["stats"]["interest"]["per_year"] == pytest.approx(start * 0.02, abs=0.01)
    eng.clock = eng.clock.replace(day=20)  # 14 Tage später, Anleihen weiter in Cash
    d = await eng.refresh()
    expect = start * (1.02 ** (14 / 365) - 1)
    assert d["pillars"]["anleihen"]["value"] == pytest.approx(start + expect, abs=0.01)
    assert d["stats"]["interest"]["earned"] == pytest.approx(expect, abs=0.01)
    assert d["pillars"]["welt"]["value"] != pytest.approx(d["pillars"]["welt"]["amount"])  # investiert: keine Zinsen
    assert eng.state["pillars"]["welt"].get("interest_earned") is None


async def test_depot_interest_from_trade_republic(make_engine, monkeypatch):
    async def portfolio(self):
        return {"positions": {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0}}, "cash": 10000.0}

    async def interest(self):
        return 0.0175

    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    monkeypatch.setattr(TradeRepublic, "interest", interest)
    eng = await make_engine()
    eng.tr.cookies = {"tr_session": "s"}
    d = await eng.refresh()
    z = d["stats"]["interest"]
    assert z["source"] == "trade_republic" and z["rate"] == 0.0175
    assert z["cash"] == 10000.0 and z["per_year"] == 175.0
    assert build_states(d)["sensor.saeulenwaechter_zins"]["state"] == 1.75


# ------------------------------------------------------------------ echtes Depot

async def test_depot_actions_recognition_and_expired_login(make_engine, sent, market, monkeypatch):
    depot = {"positions": {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0},
                           "LU0290355717": {"size": 140.0, "avg_buy": 220.0}}, "cash": 30000.0}

    async def portfolio(self):
        if isinstance(depot, Exception):
            raise depot
        return depot

    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    eng = await make_engine()
    eng.tr.cookies = {"tr_session": "s", "tr_refresh": "r"}
    d = await eng.refresh()
    assert d["mode"] == "depot"
    actions = {k: p["action"] for k, p in d["pillars"].items()}
    assert actions == {"welt": "hold", "gold": "buy", "anleihen": "sell"}
    todo = {t["key"]: t["text"] for t in d["todo"]}
    assert todo["gold"].startswith("KAUFEN: Xetra-Gold") and todo["anleihen"].startswith("KOMPLETT VERKAUFEN")
    assert "KOMPLETT VERKAUFEN: Xtrackers Eurozone Gov Bond" in sent[-1]

    # umgesetzt
    depot["positions"] = {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0},
                          "DE000A0S9GB0": {"size": 250.0, "avg_buy": 118.5}}
    n = len(sent)
    assert not eng.tr.logged_in  # nach dem Abgleich ist die Session wieder zu
    eng.tr.cookies = {"tr_session": "s"}  # neu synchronisieren
    d = await eng.refresh()
    assert d["todo"] == [] and len(sent) == n + 1 and sent[-1].count("umgesetzt") == 2

    # gleichwertige Produkte und eine unbekannte Aktie
    market["IE000VAHT5T0"] = {"price": {"bid": 4.46, "ask": 4.47, "last": 4.46}, "name": "FTSE Global All-Cap USD (Acc)"}
    market["JE00BN2CJ301"] = {"price": {"bid": 366.0, "ask": 366.1, "last": 366.0}, "name": "Core Physical Gold USD"}
    market["US0378331005"] = {"price": {"bid": 200.0, "ask": 200.2, "last": 200.0}, "name": "Apple"}
    depot["positions"] = {"IE000VAHT5T0": {"size": 9000.0, "avg_buy": 4.3},
                          "JE00BN2CJ301": {"size": 80.0, "avg_buy": 350.0},
                          "US0378331005": {"size": 5.0, "avg_buy": 180.0}}
    eng.tr.cookies = {"tr_session": "s"}
    d = await eng.refresh()
    assert d["pillars"]["welt"]["action"] == "hold" and d["pillars"]["gold"]["action"] == "hold"
    assert d["pillars"]["welt"]["held"][0]["counts_as_name"] == "SPDR MSCI ACWI IMI"
    assert [u["isin"] for u in d["depot"]["unassigned"]] == ["US0378331005"]
    assert "nicht zugeordnet: Apple (US0378331005)" in sent[-1]
    stats = {r["key"]: r for r in d["stats"]["rows"]}
    assert stats["gold"]["pnl"] == pytest.approx(80 * (366.0 - 350.0))
    split = d["tr_split"]
    assert split["base"] == pytest.approx(9000 * 4.46 + 80 * 366.0 + 30000.0)

    # eigene Zusatz-ISIN aus den Optionen
    eng2 = await make_engine({"extra_welt": "us0378331005"})
    eng2.tr.cookies = {"tr_session": "s"}
    d = await eng2.refresh()
    assert d["depot"]["unassigned"] == []
    assert {h["isin"] for h in d["pillars"]["welt"]["held"]} == {"IE000VAHT5T0", "US0378331005"}

    # Login abgelaufen: genau eine Meldung, keine Handlungsanweisung
    # seit wann gehalten: ab dem ersten Abgleich, von Hand korrigierbar
    held = {h["isin"]: h for h in eng2.data["pillars"]["welt"]["held"]}
    assert held["IE000VAHT5T0"]["since"] == "2026-10-06" and not held["IE000VAHT5T0"]["since_manual"]
    await eng2.set_held_since("IE000VAHT5T0", "2024-03-15")
    held = {h["isin"]: h for h in eng2.data["pillars"]["welt"]["held"]}
    assert held["IE000VAHT5T0"]["since"] == "2024-03-15" and held["IE000VAHT5T0"]["since_manual"]
    with pytest.raises(ValueError):
        await eng2.set_held_since("IE000VAHT5T0", "2030-01-01")

    # ohne Session: es gilt der gespeicherte Stand, mit aktuellen Kursen
    d = await eng2.refresh()
    assert d["mode"] == "depot" and d["depot"]["synced_at"] and d["depot"]["error"] is None
    assert {h["isin"] for h in d["pillars"]["welt"]["held"]} == {"IE000VAHT5T0", "US0378331005"}

    # Login beim Neu-Synchronisieren abgelaufen: genau eine Meldung, der alte Stand bleibt
    depot = TRAuthError("abgelaufen")
    eng2.tr.cookies = {"tr_session": "s"}
    d = await eng2.refresh()
    assert d["depot"]["error"] == "auth" and not eng2.tr.logged_in
    assert "Login abgelaufen" in sent[-1] and "Säulenwächter-App" in sent[-1]
    assert d["depot"]["synced_at"]
    eng2.tr.cookies = {"tr_session": "s"}
    await eng2.refresh()
    assert sum("Login abgelaufen" in s for s in sent) == 1


# ------------------------------------------------------------------ Weboberfläche

async def test_web_data_actions_and_login(make_engine, sent, aiohttp_client, monkeypatch):
    eng = await make_engine()
    changes = []

    async def changed():
        changes.append(1)

    client = await aiohttp_client(make_app(eng, changed, allowed=()))
    assert (await client.get("/api/data")).status == 503  # noch keine Daten
    html = await (await client.get("/")).text()
    assert "saeulenwaechter-panel" in html and 'src="saeulenwaechter-card.js"' in html
    assert (await client.get("/saeulenwaechter-card.js")).status == 200

    r = await client.post("/api/action", json={"action": "refresh"})
    assert r.status == 200 and changes
    data = await (await client.get("/api/data")).json()
    assert set(data["pillars"]) == {"welt", "gold", "anleihen"} and data["login"]["logged_in"] is False
    assert "events" not in data

    await client.post("/api/action", json={"action": "test"})
    assert "Testnachricht" in sent[-1]
    assert (await client.post("/api/action", json={"action": "nope"})).status == 400

    # Login: Eingaben prüfen, App-Bestätigung, Session übernehmen
    r = await client.post("/api/login/start", json={"phone": "0170 1234567", "pin": "12"})
    assert r.status == 400

    async def login_start(self, phone, pin):
        assert phone == "+491701234567" and pin == "7391"
        return "APP_CONFIRMATION"

    confirmed = {"ok": False}

    async def login_complete(self, code=None, wait=20.0):
        if not confirmed["ok"]:
            raise TRAuthError("noch nicht bestätigt")
        self.cookies = {"tr_session": "s", "tr_refresh": "r"}
        self.sec_acc_no = "123"

    async def portfolio(self):
        return {"positions": {}, "cash": 1000.0}

    monkeypatch.setattr(TradeRepublic, "login_start", login_start)
    monkeypatch.setattr(TradeRepublic, "login_complete", login_complete)
    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    r = await client.post("/api/login/start", json={"phone": "0170 1234567", "pin": "7391"})
    assert (await r.json()) == {"kind": "APP_CONFIRMATION"}
    r = await client.post("/api/login/complete", json={})
    assert r.status == 409  # erst in der App bestätigen
    confirmed["ok"] = True
    r = await client.post("/api/login/complete", json={})
    assert r.status == 200
    status = await (await client.get("/api/login")).json()
    assert not status["logged_in"] and status["synced_at"] and status["phone"] == "+491701234567"
    assert eng.data["mode"] == "depot" and eng.state["cookies"] == {}  # synchronisiert, Session geschlossen
    assert '"7391"' not in json.dumps(eng.state) and "pin" not in eng.state  # die PIN wird nie gespeichert

    # abgelehnter Authenticator-Code: Oberfläche bleibt im Code-Schritt
    async def code_rejected(self, code=None, wait=20.0):
        from sw.tr_api import TRCodeRejected
        raise TRCodeRejected("Der Code wurde nicht angenommen")

    monkeypatch.setattr(TradeRepublic, "login_complete", code_rejected)
    await client.post("/api/login/start", json={"phone": "0170 1234567", "pin": "7391"})
    r = await client.post("/api/login/complete", json={"code": "111111"})
    assert r.status == 409 and (await r.json())["step"] == "code"
    assert eng.login_status()["pending"]  # Vorgang bleibt offen, neuer Code möglich

    await client.post("/api/logout", json={})
    assert not (await (await client.get("/api/login")).json())["logged_in"]
    assert eng.data["mode"] == "paper"


async def test_web_only_reachable_through_ingress(make_engine, aiohttp_client):
    eng = await make_engine()
    client = await aiohttp_client(make_app(eng, allowed=("172.30.32.2",)))
    assert (await client.get("/api/data")).status == 403
    assert (await client.get("/")).status == 403
    assert (await client.get("/api/health")).status == 200  # Watchdog des Supervisors


# ------------------------------------------------------------------ Übertragung an Home Assistant

async def test_states_for_home_assistant(make_engine, aiohttp_client):
    eng = await make_engine()
    d = await eng.refresh()
    states = build_states(d)
    assert states["sensor.saeulenwaechter_welt_zustand"]["state"] == "Investiert"
    assert states["sensor.saeulenwaechter_anleihen_zustand"]["state"] == "Cash"
    assert states["binary_sensor.saeulenwaechter_welt_trend"]["state"] == "on"
    assert states["binary_sensor.saeulenwaechter_rezession_yield_curve"]["state"] == "on"
    assert states["sensor.saeulenwaechter_modus"]["state"] == "Papierdepot"
    assert states["binary_sensor.saeulenwaechter_handlung_noetig"]["state"] == "off"
    assert 99_000 < states["sensor.saeulenwaechter_depotwert"]["state"] < 101_000
    assert states["sensor.saeulenwaechter_depotwert"]["attributes"]["unit_of_measurement"] == "EUR"
    json.dumps(states)  # alles serialisierbar

    got = {}

    async def set_state(request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == "Bearer token"
        got[request.match_info["entity_id"]] = await request.json()
        return web.json_response({}, status=201)

    app = web.Application()
    app.router.add_post("/core/api/states/{entity_id}", set_state)
    server = await aiohttp_client(app)
    async with aiohttp.ClientSession() as http:
        pub = HomeAssistantPublisher(http, token="token", url=str(server.make_url("/core/api")))
        assert await pub.publish(d) == len(states)
        assert got["sensor.saeulenwaechter_gold_zustand"]["state"] == "Investiert"
        assert await HomeAssistantPublisher(http, token="").publish(d) == 0  # ohne Token: nichts


# ------------------------------------------------------------------ physisches Gold

async def test_physical_gold_counts_into_gold_pillar(make_engine, market, monkeypatch):
    eng = await make_engine()
    price = market["DE000A0S9GB0"]["price"]["bid"]
    await eng.add_physical_gold("1 oz Krügerrand", 1, "oz", 916.7, 2500.0, "2024-03-01")
    entry = eng.state["physical_gold"][0]
    assert entry["fine_grams"] == pytest.approx(31.1034768 * 0.9167, abs=1e-3)
    d = eng.data
    gold = d["pillars"]["gold"]
    phys_value = entry["fine_grams"] * price
    assert gold["physical_value"] == pytest.approx(phys_value)
    # Papierdepot kauft nur, was das physische Gold nicht abdeckt
    paper = [h for h in gold["held"] if not h.get("physical")][0]
    assert paper["cost"] == pytest.approx(30000 - phys_value, abs=1)
    assert gold["value"] == pytest.approx(30000, rel=0.01)
    assert {p["name"] for p in d["tr_split"]["rows"][1]["parts"]} >= {"Physisches Gold · 1 oz Krügerrand"}
    stats = {r["key"]: r for r in d["stats"]["rows"]}
    assert stats["gold"]["cost"] == pytest.approx(paper["cost"] + 2500.0)
    assert d["physical_gold"]["value"] == pytest.approx(phys_value)
    assert (await eng.remove_physical_gold(entry["id"])) and eng.state["physical_gold"] == []


async def test_physical_gold_in_depot_instructions(make_engine, market, monkeypatch):
    depot = {"positions": {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0}}, "cash": 30000.0}

    async def portfolio(self):
        return depot

    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    eng = await make_engine()
    eng.tr.cookies = {"tr_session": "s"}
    price = market["DE000A0S9GB0"]["price"]["bid"]
    await eng.add_physical_gold("Barren", 100, "g", 999.9, 9000.0)
    gold = eng.data["pillars"]["gold"]
    assert gold["action"] == "buy"
    total = sum(x["value"] for x in eng.data["pillars"].values())  # echtes Depot inkl. physischem Gold
    assert gold["buy_budget"] == pytest.approx(total * 0.3 - 100 * 0.9999 * price, abs=0.01)
    assert "schon abgezogen" in gold["instruction"]
    # deckt das Gold die Säule ab, ist nichts zu kaufen
    await eng.add_physical_gold("Großbarren", 1000, "g", 999.9, 90000.0)
    assert eng.data["pillars"]["gold"]["action"] == "hold"


async def test_depot_empty_pillars_use_tr_cash(make_engine, monkeypatch):
    # Säulen ohne Position zählen mit ihrem Anteil am echten Cash, nicht mit dem konfigurierten Betrag
    async def portfolio(self):
        return {"positions": {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0}}, "cash": 6000.0}

    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    eng = await make_engine()
    eng.tr.cookies = {"tr_session": "s"}
    await eng.refresh()
    p = eng.data["pillars"]
    assert p["gold"]["value"] == pytest.approx(3000.0)
    assert p["anleihen"]["value"] == pytest.approx(3000.0)
    assert eng.data["stats"]["total"]["value"] == pytest.approx(p["welt"]["value"] + 6000.0)
    # Beträge und Kaufbudget folgen dem echten Depotwert, nicht dem eingestellten Gesamtbetrag (100.000 €)
    total = p["welt"]["value"] + 6000.0
    assert p["gold"]["amount"] == pytest.approx(total * 0.3, abs=0.01)
    assert p["gold"]["buy_budget"] == pytest.approx(total * 0.3, abs=0.01)
    # Reserve außerhalb der Strategie: zählt nicht zu den Säulen
    eng2 = await make_engine({"cash_reserve": 4000})
    d2 = await eng2.refresh()
    assert d2["pillars"]["anleihen"]["value"] == pytest.approx(1000.0)
    r = eng.data["reconcile"]
    assert r["cash"] == 6000.0 and r["counted"] == pytest.approx(p["welt"]["value"]) and r["unassigned"] == 0


async def test_depot_uses_trade_republic_values(make_engine, market, monkeypatch):
    # Bewertet wie Trade Republic, unbekannte Positionen werden im Abgleich ausgewiesen
    async def portfolio(self):
        return {"positions": {"IE00B3YLTY66": {"size": 100.0, "avg_buy": 10.0, "tr_value": 1234.0},
                              "US0378331005": {"size": 10.0, "avg_buy": 150.0, "tr_value": 2000.0}}, "cash": 500.0}

    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    eng = await make_engine()
    eng.tr.cookies = {"tr_session": "s"}
    d = await eng.refresh()
    bid = market["IE00B3YLTY66"]["price"]["bid"]
    assert d["pillars"]["welt"]["value"] == pytest.approx(100 * bid)  # aktueller Kurs
    assert d["depot"]["unassigned"][0]["value"] == pytest.approx(2000.0)  # ohne Kurs: Wert von TR
    r = d["reconcile"]
    assert r["tr_positions"] == 3234.0 and r["unassigned"] == pytest.approx(2000.0)


async def test_web_gold_api(make_engine, aiohttp_client):
    eng = await make_engine()
    client = await aiohttp_client(make_app(eng, allowed=()))
    assert (await client.post("/api/gold", json={"qty": 0})).status == 400
    r = await client.post("/api/gold", json={"name": "Münze", "qty": "1,5", "unit": "oz", "fineness": "999,9",
                                             "cost": "3.900,50"})
    assert r.status == 200
    entry = await r.json()
    assert entry["cost"] == 3900.5 and entry["qty"] == 1.5
    g = await (await client.get("/api/gold")).json()
    assert len(g["items"]) == 1 and g["price_g"] > 0 and g["value"] > 0
    assert (await client.delete(f"/api/gold/{entry['id']}")).status == 200
    assert (await client.delete("/api/gold/nope")).status == 404


# ------------------------------------------------------------------ QR-Login

async def test_web_qr_login(make_engine, aiohttp_client, monkeypatch):
    eng = await make_engine()
    polls = iter([{"status": "PENDING", "qrCodePayload": "https://traderepublic.com/web-login/challenge?c=1&t=a"},
                  {"status": "CLAIMED", "processId": "p1"}])

    async def qr_start(self):
        self._qr_challenge = "c1"
        return {"challengeId": "c1"}

    async def qr_poll(self):
        body = next(polls)
        if body["status"] == "CLAIMED":
            self._process_id = body["processId"]
        return body

    async def qr_complete(self, wait=120.0):
        self.cookies = {"tr_session": "s", "tr_refresh": "r"}
        self.sec_acc_no = "9"

    async def portfolio(self):
        return {"positions": {}, "cash": 500.0}

    for name, fn in (("qr_start", qr_start), ("qr_poll", qr_poll), ("qr_complete", qr_complete),
                     ("portfolio", portfolio)):
        monkeypatch.setattr(TradeRepublic, name, fn)
    client = await aiohttp_client(make_app(eng, allowed=()))
    r = await (await client.post("/api/login/qr", json={})).json()
    assert r["status"] == "pending" and r["svg"].startswith("<svg viewBox=")  # skaliert ohne Verzerrung
    r = await (await client.get("/api/login/qr")).json()
    assert r["status"] == "claimed"
    await eng._qr["task"]
    r = await (await client.get("/api/login/qr")).json()
    assert r["status"] == "done"
    assert not eng.login_status()["logged_in"] and eng.login_status()["synced_at"]
    assert eng.state["login_method"] == "qr"
    assert eng.data["mode"] == "depot"


def test_page_and_card_share_no_global_names():
    """Seite und Karte laufen als klassische Skripte im selben globalen Bereich – doppelte Namen brechen die Seite."""
    import re
    www = Path(__file__).parents[1] / "saeulenwaechter" / "app" / "www"
    page = (www / "index.html").read_text()
    card = (www / "saeulenwaechter-card.js").read_text()
    names = re.compile(r"^\s*(?:const|let|var|function|async function|class)\s+([A-Za-z_$][\w$]*)", re.M)
    page_top = set(names.findall("\n".join(re.findall(r"<script>(.*?)</script>", page, re.S))))
    card_top = set(re.findall(r"^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", card, re.M))
    assert not page_top & card_top


async def test_cash_rate_falls_back_to_ecb_deposit_rate(make_engine):
    eng = await make_engine()
    d = await eng.refresh()
    z = d["stats"]["interest"]
    assert z["source"] == "ezb" and z["rate"] == pytest.approx(0.02) and z["at"] == "2026-10-05"


async def test_ha_service_notification(aiohttp_client):
    """Meldungen über einen Dienst in Home Assistant (z. B. ha-whatsapp)."""
    from sw.notify import send_ha_service
    calls = []

    async def service(request):
        calls.append((request.match_info["domain"], request.match_info["name"],
                      request.headers.get("Authorization"), await request.json()))
        return web.json_response([])

    app = web.Application()
    app.router.add_post("/core/api/services/{domain}/{name}", service)
    client = await aiohttp_client(app)
    url = str(client.make_url("/core/api"))
    assert await send_ha_service(client.session, "whatsapp.send_message", "+49 171 1234567", "Hallo", "t", url)
    assert calls[-1] == ("whatsapp", "send_message", "Bearer t", {"message": "Hallo", "target": "+491711234567"})
    assert await send_ha_service(client.session, "notify.mobile_app_handy", None, "Hallo", "t", url)
    assert calls[-1][3] == {"message": "Hallo", "title": "Säulenwächter"}
    assert not await send_ha_service(client.session, "kaputt", None, "x", "t", url)


async def test_performance_periods_and_series(make_engine, market):
    eng = await make_engine()
    d = await eng.refresh()
    perf = d["performance"]
    assert list(perf["periods"]) == ["1W", "1M", "3M", "6M", "YTD", "1J", "3J", "5J", "MAX"]
    one = perf["periods"]["1M"]
    assert one["from"] <= "2026-09-06" and isinstance(one["gain"], float)
    assert perf["periods"]["YTD"]["from"] <= "2026-01-02"
    # jede Zeile: Tag, gesamt, je Säule – die Summe der Säulen ergibt den Gesamtwert
    assert perf["keys"] == ["welt", "gold", "anleihen"]
    last = perf["series"][-1]
    assert last[0] == "2026-10-06" and last[1] == pytest.approx(sum(last[2:]), abs=0.05)
    invested_positions = sum(h["value"] for p in d["pillars"].values() for h in p["held"])
    assert last[1] == pytest.approx(invested_positions, abs=1)  # Wertpapiere ohne Cash
    assert one["gain"] == pytest.approx(sum(one["pillars"].values()), abs=0.05)

def test_normalize_target():
    from sw.notify import normalize_target
    assert normalize_target("0171 123-4567") == "+491711234567"
    assert normalize_target("0049 171 1234567") == "+491711234567"
    assert normalize_target("491711234567") == "+491711234567"
    assert normalize_target("120363000000000000@g.us") == "120363000000000000@g.us"
    assert normalize_target("") is None



async def test_performance_uses_trade_history(make_engine, market, monkeypatch):
    """Echter Verlauf: Stückzahlen je Tag aus den Käufen, Käufe zählen nicht als Gewinn, Haltedauer aus dem 1. Kauf."""
    async def portfolio(self):
        return {"positions": {"IE00B3YLTY66": {"size": 100.0, "avg_buy": 10.0}}, "cash": 0.0}

    async def transactions(self, isins=None, max_pages=60):
        return [{"id": "a", "isin": "IE00B3YLTY66", "time": "2026-03-02T10:00:00+00:00", "date": "2026-03-02",
                 "amount": -600.0, "shares": 60.0, "title": "SPDR", "subtitle": "Kauforder"},
                {"id": "b", "isin": "IE00B3YLTY66", "time": "2026-09-21T10:00:00+00:00", "date": "2026-09-21",
                 "amount": -450.0, "shares": 40.0, "title": "SPDR", "subtitle": "Sparplan ausgeführt"}]

    monkeypatch.setattr(TradeRepublic, "portfolio", portfolio)
    monkeypatch.setattr(TradeRepublic, "transactions", transactions)
    eng = await make_engine()
    eng.tr.cookies = {"tr_session": "s"}
    d = await eng.refresh()
    perf = d["performance"]
    assert perf["history"] is True
    rows = {r[0]: r for r in perf["series"]}
    before = max(day for day in rows if day < "2026-03-02")
    assert rows[before][1] == 0  # vor dem ersten Kauf nichts im Depot
    mid = max(day for day in rows if day < "2026-09-21")
    closes = {r[0]: r for r in perf["series"]}
    assert closes[mid][1] > 0
    one = perf["periods"]["1M"]
    assert one["invested"] == pytest.approx(450.0)
    assert one["gain"] == pytest.approx(perf["series"][-1][1] - rows[[k for k in rows if k <= one["from"]][-1]][1] - 450.0,
                                        abs=0.05)
    assert [e["amount"] for e in perf["events"]] == [600.0, 450.0]
    held = d["pillars"]["welt"]["held"][0]
    assert held["since"] == "2026-03-02" and held["since_manual"] == "trades"
