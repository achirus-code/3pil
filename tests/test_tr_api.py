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


# --- Web-Login --------------------------------------------------------------------------------

from sw.tr_api import TRCodeRejected, TRCodeRequired  # noqa: E402


def login_client(script):
    """TR-Client, dessen HTTP-Aufrufe ein Skript beantwortet: {(method, path-suffix): [answers…]}."""
    tr = TradeRepublic(session=None)
    calls = []

    async def request(method, path, *, login=False, **kw):
        calls.append((method, path.rsplit("/", 1)[-1], kw.get("json")))
        for (m, suffix), answers in script.items():
            if m == method and path.endswith(suffix):
                status, body, cookies = answers.pop(0) if len(answers) > 1 else answers[0]
                tr.cookies.update(cookies)
                return status, body
        raise AssertionError(f"unerwartet: {method} {path}")

    async def no_sleep(_):
        return None

    tr._request = request
    return tr, calls, no_sleep


async def test_rejected_code_can_be_retried_and_session_is_polled(monkeypatch):
    import asyncio
    tr, calls, no_sleep = login_client({
        ("POST", "/api/v2/auth/web/login"): [(200, {"processId": "p1"}, {})],
        ("POST", "/authenticator-verification"): [
            (401, {"errors": [{"errorCode": "AUTHENTICATION_ERROR"}]}, {}),
            (200, {}, {})],
        ("GET", "/processes/p1"): [
            (200, {"status": "PENDING", "requiredAction": "AUTHENTICATOR_VERIFICATION"}, {}),
            (200, {"status": "PENDING"}, {}),
            (200, {"status": "COMPLETED"}, {"tr_session": "s", "tr_refresh": "r"})],
        ("GET", "/api/v2/auth/account"): [(200, {"securitiesAccountNumber": "42"}, {})],
    })
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    assert await tr.login_start("+491701234567", "7391") == "AUTHENTICATOR_VERIFICATION"
    with pytest.raises(TRCodeRejected, match="nicht angenommen"):
        await tr.login_complete(code="123 456")
    assert ("POST", "authenticator-verification", {"code": "123456"}) in calls  # Leerzeichen entfernt
    await tr.login_complete(code="654321")  # gleicher Vorgang, neuer Code
    assert tr.cookies["tr_session"] == "s" and tr.sec_acc_no == "42"


async def test_short_code_is_refused_without_asking_trade_republic():
    tr, calls, _ = login_client({})
    tr._process_id, tr.required_action = "p1", "AUTHENTICATOR_VERIFICATION"
    with pytest.raises(TRCodeRejected):
        await tr.login_complete(code="12")
    assert calls == []


async def test_app_confirmation_switches_to_code_when_asked(monkeypatch):
    import asyncio
    tr, _, no_sleep = login_client({
        ("POST", "/api/v2/auth/web/login"): [(200, {"processId": "p1"}, {})],
        ("GET", "/processes/p1"): [
            (200, {"status": "PENDING"}, {}),
            (200, {"status": "PENDING", "requiredAction": "AUTHENTICATOR_VERIFICATION"}, {})],
    })
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    assert await tr.login_start("+491701234567", "7391") == "APP_CONFIRMATION"
    with pytest.raises(TRCodeRequired):
        await tr.login_complete()
    assert tr.required_action == "AUTHENTICATOR_VERIFICATION"


async def test_qr_challenge_flow(monkeypatch):
    import asyncio
    tr, calls, no_sleep = login_client({
        ("POST", "/qr-challenges"): [(200, {"challengeId": "c1", "challengeExpiresAt": "x"}, {"JSESSIONID": "j"})],
        ("GET", "/qr-challenges/c1"): [
            (200, {"status": "PENDING", "qrCodePayload": "https://traderepublic.com/web-login/challenge?t=1"}, {}),
            (200, {"status": "CLAIMED", "processId": "p9"}, {})],
        ("GET", "/processes/p9"): [(200, {"status": "COMPLETED"}, {"tr_session": "s", "tr_refresh": "r"})],
        ("GET", "/api/v2/auth/account"): [(200, {"securitiesAccountNumber": "7"}, {})],
    })
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    await tr.qr_start()
    assert tr.cookies["JSESSIONID"] == "j"
    assert (await tr.qr_poll())["status"] == "PENDING"
    assert (await tr.qr_poll())["status"] == "CLAIMED"
    await tr.qr_complete()
    assert tr.cookies["tr_session"] == "s" and tr.sec_acc_no == "7"


async def test_qr_expired_and_throttled():
    tr, _, _ = login_client({
        ("GET", "/qr-challenges/c1"): [
            (429, {"errors": [{"errorCode": "TOO_MANY_REQUESTS"}]}, {}),
            (410, {"errors": [{"errorCode": "PROCESS_GONE"}]}, {})],
    })
    tr._qr_challenge = "c1"
    assert (await tr.qr_poll())["status"] == "PENDING"
    assert (await tr.qr_poll())["status"] == "EXPIRED"


async def test_portfolio_v2_amount_objects():
    port = {"categories": [{"positions": [{"isin": "IE00B3YLTY66", "netSize": "10",
                                           "averageBuyIn": {"value": "200.5", "currency": "EUR"},
                                           "netValue": 2125.0,
                                           "performanceSinceBuyAbsolute": {"value": "120"}}]}]}
    seen = []
    tr = client(lambda p: seen.append(p[0]["type"]) or [port, []])
    res = await tr.portfolio()
    assert seen[0] == "compactPortfolioByTypeV2"
    assert res["positions"]["IE00B3YLTY66"] == {"size": 10.0, "avg_buy": 200.5, "tr_value": 2125.0,
                                                    "tr_pnl": 120.0}


def test_find_rate():
    from sw.tr_api import find_rate
    assert find_rate({"interestRate": 2.0}) == pytest.approx(0.02)
    assert find_rate({"details": {"rate": {"value": "1.75"}}}) == pytest.approx(0.0175)
    assert find_rate([{"x": 1}, {"interestRate": 0.02}]) == pytest.approx(0.02)
    assert find_rate({"foo": "bar"}) is None
