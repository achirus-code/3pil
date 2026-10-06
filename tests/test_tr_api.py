"""Depot-Auswertung von Trade Republic (ohne Netzwerk)."""

import pytest

from sw.tr_api import TradeRepublic


def client(answer):
    tr = TradeRepublic(session=None, cookies={"tr_session": "s"}, sec_acc_no="1")

    async def refresh_session():
        return None

    async def fetch(payloads, auth=False, timeout=25.0):
        return answer(payloads)

    tr.refresh_session = refresh_session
    tr.fetch = fetch
    return tr


async def test_portfolio_merges_categories_and_ignores_flat_list():
    port = {"categories": [
        {"positions": [{"isin": "IE00B3YLTY66", "netSize": "100", "averageBuyIn": "10"}]},
        {"positions": [{"isin": "IE00B3YLTY66", "netSize": "50", "averageBuyIn": "13"},
                       {"isin": "JE00BN2CJ301", "netSize": "2", "averageBuyIn": None}]}],
        "positions": [{"isin": "IE00B3YLTY66", "netSize": "100", "averageBuyIn": "10"}]}
    tr = client(lambda p: [port, [{"currencyId": "EUR", "amount": "1234.5"}]])
    res = await tr.portfolio()
    assert res["positions"]["IE00B3YLTY66"] == {"size": 150.0, "avg_buy": pytest.approx(11.0)}
    assert res["positions"]["JE00BN2CJ301"] == {"size": 2.0, "avg_buy": None}
    assert res["cash"] == 1234.5


async def test_portfolio_flat_fallback_and_unknown_average():
    port = {"positions": [{"instrumentId": "DE000A0S9GB0", "netSize": "3", "averageBuyIn": "100"},
                          {"instrumentId": "DE000A0S9GB0", "netSize": "1", "averageBuyIn": None}]}
    tr = client(lambda p: [port, []])
    res = await tr.portfolio()
    assert res["positions"]["DE000A0S9GB0"] == {"size": 4.0, "avg_buy": None}
