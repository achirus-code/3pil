"""Integrationstest in einer echten Home-Assistant-Instanz mit aufgezeichneten Live-Daten."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.saeulenwaechter import macro
from custom_components.saeulenwaechter.const import DOMAIN

FIXTURE = json.loads((Path(__file__).parents[1] / "tests" / "fixture_live.json").read_text())


@pytest.fixture
def sent():
    return []


@pytest.fixture
def mocked(sent):
    async def market_data(self, isins, exchange, candles=True, names=True):
        out = {}
        for i in isins:
            d = FIXTURE["market"].get(i, {})
            out[i] = {"price": d.get("price")}
            if candles:
                out[i]["candles"] = d.get("candles")
            if names:
                out[i]["name"] = d.get("name")
        return out

    def fetcher(key):
        async def f(session, *a):
            return FIXTURE["macro"][key]
        return f

    async def send(session, phone, apikey, text):
        sent.append(text)
        return True

    with patch("custom_components.saeulenwaechter.tr_api.TradeRepublic.market_data", market_data), \
         patch.dict(macro.FETCHERS, {k: fetcher(k) for k in macro.FETCHERS}), \
         patch("custom_components.saeulenwaechter.coordinator.send_whatsapp", send):
        yield


async def _setup(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "paper"})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "notify"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"wa_phone": "4917000000", "wa_apikey": "test", "total": 100000})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


async def test_paper_setup_decision_and_messages(hass, mocked, sent, freezer, hass_ws_client, hass_admin_user):
    freezer.move_to("2026-10-06 08:00:00+00:00")  # Di. 10:00 Berlin, Börse offen
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry = await _setup(hass)

    assert hass.states.get("sensor.saeulenwaechter_welt_zustand").state == "Investiert"
    assert hass.states.get("sensor.saeulenwaechter_gold_zustand").state == "Investiert"
    assert hass.states.get("sensor.saeulenwaechter_anleihen_zustand").state == "Cash"
    assert hass.states.get("binary_sensor.saeulenwaechter_welt_trend").state == "on"
    assert hass.states.get("binary_sensor.saeulenwaechter_rezession_yield_curve").state == "on"
    assert hass.states.get("sensor.saeulenwaechter_modus").state == "Papierdepot"
    total = float(hass.states.get("sensor.saeulenwaechter_depotwert").state)
    assert 99_000 < total < 101_000
    attrs = hass.states.get("sensor.saeulenwaechter_welt_zustand").attributes
    assert attrs["signale"][0]["title"] == "Entscheidung Okt. 2026"
    assert float(hass.states.get("sensor.saeulenwaechter_welt_umschaltkurs").state) > 0

    # Willkommen + Monatsentscheidung in einer Nachricht
    assert len(sent) == 1
    print("\n----- WhatsApp #1 -----\n" + sent[0])
    assert "Monatsentscheidung Okt. 2026" in sent[0]

    # Nochmal aktualisieren: nichts Neues → keine Nachricht
    coord = hass.data[DOMAIN][entry.entry_id]
    await coord.async_refresh()
    assert len(sent) == 1

    # Websocket für Karte/Panel
    # Token zur eingefrorenen Zeit ausstellen (das Fixture-Token entsteht zur echten Uhrzeit)
    refresh = await hass.auth.async_create_refresh_token(hass_admin_user, "https://example.com/app")
    ws = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
    await ws.send_json({"id": 1, "type": "saeulenwaechter/data"})
    msg = await ws.receive_json()
    assert msg["success"]
    assert set(msg["result"]["pillars"]) == {"welt", "gold", "anleihen"}
    assert msg["result"]["pillars"]["welt"]["held"][0]["isin"] == "IE00B3YLTY66"
    import os
    if os.environ.get("SW_DUMP"):
        Path(os.environ["SW_DUMP"]).write_text(json.dumps(msg["result"]))

    # Neuer Monat → neue Entscheidung, Monatsbericht
    freezer.move_to("2026-11-02 08:00:00+00:00")
    await coord.async_refresh()
    assert len(sent) == 2
    print("\n----- WhatsApp #2 -----\n" + sent[1])
    assert "Monatsentscheidung Nov. 2026" in sent[1]
    hist = hass.states.get("sensor.saeulenwaechter_welt_zustand").attributes["historie"]
    assert [h["month"] for h in hist] == ["2026-10", "2026-11"]

    # Test-Button
    await hass.services.async_call("button", "press", {"entity_id": "button.saeulenwaechter_testnachricht"},
                                   blocking=True)
    assert "Testnachricht" in sent[-1]

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_depot_login_actions_and_reauth(hass, mocked, sent, freezer, monkeypatch):
    from custom_components.saeulenwaechter.tr_api import TRAuthError

    freezer.move_to("2026-10-06 08:00:00+00:00")
    await hass.config.async_set_time_zone("Europe/Berlin")
    depot = {"positions": {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0},
                           "LU0290355717": {"size": 140.0, "avg_buy": 220.0}}, "cash": 30000.0}

    async def login_start(self, phone, pin):
        assert phone == "+491701234567" and pin == "1234"
        return "APP_CONFIRMATION"

    async def login_complete(self, code=None, wait=20.0):
        self.cookies = {"tr_session": "s", "tr_refresh": "r"}
        self.sec_acc_no = "123"

    async def portfolio(self):
        if isinstance(depot, Exception):
            raise depot
        return depot

    with patch("custom_components.saeulenwaechter.tr_api.TradeRepublic.login_start", login_start), \
         patch("custom_components.saeulenwaechter.tr_api.TradeRepublic.login_complete", login_complete), \
         patch("custom_components.saeulenwaechter.tr_api.TradeRepublic.portfolio", portfolio):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "login"})
        assert result["step_id"] == "login"
        result = await hass.config_entries.flow.async_configure(result["flow_id"],
                                                                {"phone": "0170 1234567", "pin": "1234"})
        assert result["step_id"] == "confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "notify"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"wa_phone": "4917000000", "wa_apikey": "test", "total": 100000})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        entry = result["result"]
        assert "pin" not in entry.data
        await hass.async_block_till_done()

        assert hass.states.get("sensor.saeulenwaechter_modus").state == "Echtes Depot"
        assert hass.states.get("binary_sensor.saeulenwaechter_trade_republic").state == "on"
        assert hass.states.get("sensor.saeulenwaechter_welt_aktion").state == "halten"
        assert hass.states.get("sensor.saeulenwaechter_gold_aktion").state == "kaufen"
        assert hass.states.get("sensor.saeulenwaechter_anleihen_aktion").state == "verkaufen"
        print("\n----- WhatsApp Depot #1 -----\n" + sent[-1])
        assert "KOMPLETT VERKAUFEN: Xtrackers Eurozone Gov Bond" in sent[-1]
        assert "KAUFEN: Xetra-Gold" in sent[-1]

        # Nutzer hat umgesetzt
        n = len(sent)
        depot["positions"] = {"IE00B3YLTY66": {"size": 3350.0, "avg_buy": 11.0},
                              "DE000A0S9GB0": {"size": 250.0, "avg_buy": 118.5}}
        coord = hass.data[DOMAIN][entry.entry_id]
        await coord.async_refresh()
        assert len(sent) == n + 1
        print("\n----- WhatsApp Depot #2 -----\n" + sent[-1])
        assert sent[-1].count("umgesetzt") == 2

        # Positionen werden per ISIN erkannt: Vanguard zählt wie SPYI, WisdomTree wie Xetra-Gold,
        # eine Einzelaktie gehört zu keiner Säule
        monkeypatch.setitem(FIXTURE["market"], "IE000VAHT5T0",
                            {"price": {"bid": 4.46, "ask": 4.47, "last": 4.46}, "name": "FTSE Global All-Cap USD (Acc)"})
        monkeypatch.setitem(FIXTURE["market"], "JE00BN2CJ301",
                            {"price": {"bid": 366.0, "ask": 366.1, "last": 366.0}, "name": "Core Physical Gold USD"})
        monkeypatch.setitem(FIXTURE["market"], "US0378331005",
                            {"price": {"bid": 200.0, "ask": 200.2, "last": 200.0}, "name": "Apple"})
        depot["positions"] = {"IE000VAHT5T0": {"size": 9000.0, "avg_buy": 4.3},
                              "JE00BN2CJ301": {"size": 80.0, "avg_buy": 350.0},
                              "US0378331005": {"size": 5.0, "avg_buy": 180.0}}
        await coord.async_refresh()
        assert hass.states.get("sensor.saeulenwaechter_welt_aktion").state == "halten"
        assert hass.states.get("sensor.saeulenwaechter_gold_aktion").state == "halten"
        welt = coord.data["pillars"]["welt"]["held"][0]
        assert welt["isin"] == "IE000VAHT5T0" and welt["counts_as"] == "IE00B3YLTY66"
        assert welt["counts_as_name"] == "SPDR MSCI ACWI IMI"
        attrs = hass.states.get("sensor.saeulenwaechter_modus").attributes
        assert [u["isin"] for u in attrs["nicht_zugeordnet"]] == ["US0378331005"]
        print("\n----- WhatsApp Depot #3 -----\n" + sent[-1])
        assert "nicht zugeordnet: Apple (US0378331005)" in sent[-1]
        split = attrs["tr_verteilung"]
        rows = {r["key"]: r for r in split["rows"]}
        assert split["base"] == pytest.approx(9000 * 4.46 + 80 * 366.0 + 30000.0)
        assert rows["welt"]["soll"] == pytest.approx(0.4) and rows["anleihen"]["soll"] == 0.0
        assert split["cash"]["soll"] == pytest.approx(0.3)
        assert split["unassigned_value"] == pytest.approx(1000.0)

        # Eigene Zusatz-ISIN in den Optionen: die Aktie zählt dann zur Welt-Säule
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**{k: v for k, v in result["data_schema"]({}).items()}, "extra_welt": "us0378331005, x"})
        assert entry.options["extra_welt"] == "US0378331005"
        await hass.async_block_till_done()
        coord = hass.data[DOMAIN][entry.entry_id]
        await coord.async_refresh()
        assert coord.data["depot"]["unassigned"] == []
        assert {h["isin"] for h in coord.data["pillars"]["welt"]["held"]} == {"IE000VAHT5T0", "US0378331005"}

        # Login abgelaufen → Reauth-Flow + eine Nachricht
        depot = TRAuthError("abgelaufen")
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert "Login abgelaufen" in sent[-1]
        flows = hass.config_entries.flow.async_progress()
        assert any(f["context"]["source"] == "reauth" for f in flows)
        assert hass.states.get("sensor.saeulenwaechter_gold_aktion").state == "–"
        await coord.async_refresh()
        assert sum("Login abgelaufen" in s for s in sent) == 1
