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


async def test_logout_closes_session():
    tr, calls, _ = login_client({("POST", "logout"): [(200, None, {})]})
    tr.cookies = {"tr_session": "s", "tr_refresh": "r"}
    await tr.logout()
    assert tr.cookies == {} and not tr.logged_in and calls[0][:2] == ("POST", "logout")



async def test_transactions_from_timeline():
    pages = {
        None: {"items": [
            {"id": "t1", "timestamp": "2026-09-21T08:01:02.000+0000", "title": "SPDR MSCI ACWI IMI",
             "subtitle": "Sparplan ausgeführt", "icon": "logos/IE00B3YLTY66/v2", "status": "EXECUTED",
             "amount": {"value": -450.0, "currency": "EUR"}},
            {"id": "t2", "timestamp": "2026-08-01T08:00:00.000+0000", "title": "Apple", "icon": "logos/US0378331005/v2",
             "amount": {"value": -100.0}},
            {"id": "t3", "timestamp": "2026-07-10T08:00:00.000+0000", "title": "SPDR", "subtitle": "Verkaufsorder",
             "icon": "logos/IE00B3YLTY66/v2", "amount": {"value": 1200.5}},
            # Ausschüttungen tragen dieselbe ISIN und in den Details die Stückzahl – sind aber keine Verkäufe
            {"id": "d1", "timestamp": "2026-06-15T08:00:00.000+0000", "title": "SPDR", "subtitle": "Ausschüttung",
             "icon": "logos/IE00B3YLTY66/v2", "amount": {"value": 12.3}},
            {"id": "d2", "timestamp": "2026-05-15T08:00:00.000+0000", "title": "SPDR", "subtitle": "",
             "icon": "logos/IE00B3YLTY66/v2", "amount": {"value": 9.1}, "dividend": True},
            {"id": "d3", "timestamp": "2026-04-15T08:00:00.000+0000", "title": "SPDR", "subtitle": "Gutschrift",
             "icon": "logos/IE00B3YLTY66/v2", "amount": {"value": 7.0}},
            {"id": "n1", "timestamp": "2026-04-01T08:00:00.000+0000", "title": "SPDR", "subtitle": "Kauforder",
             "icon": "logos/IE00B3YLTY66/v2", "amount": {"value": -50.0}}],
            "cursors": {"after": "c2"}},
        "c2": {"items": [{"id": "t4", "timestamp": "2026-03-02T10:00:00.000+0000", "title": "SPDR",
                          "subtitle": "Kauforder", "icon": "logos/IE00B3YLTY66/v2", "status": "CANCELED",
                          "amount": {"value": -600.0}}], "cursors": {}},
    }
    details = {"t1": {"sections": [{"title": "Transaktion", "data": [
                   {"title": "Anteile", "detail": {"text": "38,123456"}},
                   {"title": "Aktienkurs", "detail": {"text": "11,80 €"}}]}]},
               "t3": {"sections": [{"data": [{"title": "Aktien", "detail": {"text": "100"}}]}]},
               "d1": {"sections": [{"data": [{"title": "Aktien", "detail": {"text": "38"}}]}]},
               "d3": {"sections": [{"title": "Dividende", "data": [{"title": "Aktien", "detail": {"text": "38"}}]}]}}

    def answer(payloads):
        out = []
        for p in payloads:
            if p["type"] == "timelineTransactions":
                out.append(pages[p.get("after")])
            else:
                out.append(details.get(p["id"], {}))
        return out

    tr = client(answer)
    trades = await tr.transactions(isins={"IE00B3YLTY66"})
    assert [(t["id"], t["date"], t["amount"], t["shares"]) for t in trades] == [
        ("t1", "2026-09-21", -450.0, pytest.approx(38.123456)), ("t3", "2026-07-10", 1200.5, -100.0),
        ("n1", "2026-04-01", -50.0, None)]  # Kauf ohne Stückzahl: wird später aus Betrag und Kurs geschätzt
    assert trades[2]["estimated"]
    diag = tr.last_timeline
    assert diag["pages"] == 2 and diag["items"] == 8 and diag["held"] == 7 and diag["skipped"] == 2
    assert diag["with_shares"] == 2 and diag["estimated"] == 1 and "Anteile" in diag["detail_titles"]



def test_find_shares_in_transaction_row():
    from sw.tr_api import find_shares
    detail = {"sections": [{"title": "Übersicht", "data": [
        {"title": "Transaktion", "detail": {"text": "2.805,927158 × 11,51 €", "type": "text"}},
        {"title": "Gebühr", "detail": {"text": "1,00 €"}}]}]}
    assert find_shares(detail) == pytest.approx(2805.927158)
    assert find_shares({"data": [{"title": "Ausführung", "detail": {"text": "38,5 x 4,29 €"}}]}) == pytest.approx(38.5)
