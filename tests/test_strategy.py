from datetime import date

import pytest

from sw import strategy as S
from sw.const import PILLARS

WELT, GOLD, BONDS = PILLARS


def candles_from_monthly(values, last_month="2026-09"):
    """values: Monatsschlüsse, ältester zuerst. Je Monat zwei Kerzen (Mitte, Ende)."""
    out = []
    from datetime import datetime, timezone
    y, m = (int(x) for x in last_month.split("-"))
    months = []
    for _ in values:
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    for (yy, mm), v in zip(reversed(months), values):
        mid = datetime(yy, mm, 10, tzinfo=timezone.utc).timestamp() * 1000
        end = datetime(yy, mm, 27, tzinfo=timezone.utc).timestamp() * 1000
        out += [{"time": int(mid), "close": str(v * 0.9)}, {"time": int(end), "close": str(v)}]
    return out


def test_monthly_closes_newest_first_and_excludes_current_month():
    c = candles_from_monthly([1, 2, 3], last_month="2026-10")
    closes = S.monthly_closes(c, date(2026, 10, 6))
    assert closes == [("2026-09", 2.0), ("2026-08", 1.0)]


def test_monthly_closes_breaks_at_gap():
    c = candles_from_monthly([1, 2, 3, 4], last_month="2026-09")
    c = [x for x in c if not (1780000000000 > x["time"] > 1777000000000)]  # Mai 2026 entfernen
    closes = S.monthly_closes(c, date(2026, 10, 6))
    assert [m for m, _ in closes] == ["2026-09", "2026-08", "2026-07", "2026-06"][: len(closes)]
    assert all(m > "2026-05" for m, _ in closes)


def test_sma_signal_and_switch_price_roundtrip():
    closes = [110] + [100] * 9
    r = S.sma_signal(closes, prev_on=False)
    assert r["on"] is True
    # Schließt der nächste Monat genau am Umschaltkurs, liegt der Kurs auf der Grenze avg·(1−b)
    nxt = [r["switch"]] + closes[:9]
    avg = sum(nxt) / 10
    assert nxt[0] == pytest.approx(avg * (1 - S.SMA_BUFFER))


def test_sma_hysteresis_keeps_previous_state():
    closes = [101] + [100] * 9  # innerhalb ±2 %
    assert S.sma_signal(closes, prev_on=True)["on"] is True
    assert S.sma_signal(closes, prev_on=False)["on"] is False
    assert S.sma_signal(closes, prev_on=None)["on"] is False


def test_off_switch_price_turns_on():
    closes = [90] + [100] * 9
    r = S.sma_signal(closes, prev_on=True)
    assert r["on"] is False
    nxt = [r["switch"]] + closes[:9]
    assert nxt[0] == pytest.approx(sum(nxt) / 10 * (1 + S.SMA_BUFFER))


def test_hurdle_euribor_and_fallback():
    eur = {f"2025-{m:02d}": 2.4 for m in range(10, 13)} | {f"2026-{m:02d}": 2.4 for m in range(1, 10)}
    h, src = S.hurdle(eur, "2026-09")
    assert src == "Euribor"
    assert h == pytest.approx((1 + 0.024 / 12) ** 12 - 1)
    h2, src2 = S.hurdle({"2026-09": 2.0}, "2026-09")
    assert src2 == "fest" and h2 == pytest.approx(0.02)
    # negative Zinsen zählen als 0
    neg = {k: -0.5 for k in eur}
    assert S.hurdle(neg, "2026-09")[0] == 0


def test_momentum_and_switch():
    closes = [115] + [100] * 12
    r = S.momentum_signal(closes, 0.02)
    assert r["on"] and r["ret"] == pytest.approx(0.15)
    assert r["switch"] == pytest.approx(100 * 1.02)


def _ctx(closes_by_isin, macro=None, eurusd=None, today=date(2026, 10, 6)):
    return {"today": today, "closes": closes_by_isin, "euribor": None, "eurusd": eurusd, "macro": macro or {},
            "names": {}, "symbols": {}, "prices": {}}


def series(values, last="2026-09"):
    return [(S.add_months(last, -i), v) for i, v in enumerate(values)]


def test_welt_either_trend_on():
    up = series([120] + [100] * 12)
    res = S.evaluate_pillar(WELT, _ctx({WELT["isin"]: up}), {})
    assert res["trend_on"] and res["invested"] and res["state"] == "in" and res["target"] == WELT["isin"]
    keys = [r["key"] for r in res["signals"]]
    assert keys[:3] == ["decision", "sma", "mom"]
    assert keys[3:6] == ["unemployment", "claims", "yield_curve"]


def test_welt_trend_off_without_recession_stays_invested():
    down = series([80] + [100] * 12)
    macro = {k: {"key": k, "state": "ok", "title": k} for k in ("unemployment", "claims", "yield_curve")}
    res = S.evaluate_pillar(WELT, _ctx({WELT["isin"]: down}, macro), {})
    assert not res["trend_on"] and res["invested"]
    assert "bleibt investiert" in res["recession_reason"]


def test_welt_trend_off_with_recession_parks_in_best_fallback():
    down = series([80] + [100] * 12)
    macro = {"unemployment": {"key": "unemployment", "state": "warn", "title": "US-Arbeitslosenquote"},
             "claims": {"key": "claims", "state": "ok"}, "yield_curve": {"key": "yield_curve", "state": "unknown"}}
    fb1 = series([104] + [100] * 12)  # +4 % > 2 %
    fb2 = series([106] + [100] * 12)  # +6 % → beste
    res = S.evaluate_pillar(WELT, _ctx({WELT["isin"]: down, "LU0290355717": fb1, "LU1407888137": fb2}, macro), {})
    assert not res["invested"]
    assert res["state"] == "parked" and res["target"] == "LU1407888137"


def test_welt_trend_off_no_recession_data_goes_cash():
    down = series([80] + [100] * 12)
    res = S.evaluate_pillar(WELT, _ctx({WELT["isin"]: down}), {})
    assert not res["invested"] and res["state"] == "cash" and res["target"] is None


def test_welt_hedged_when_dollar_falls():
    up = series([120] + [100] * 12)
    eurusd = {S.add_months("2026-09", -i): (1.20 if i == 0 else 1.10) for i in range(12)}
    res = S.evaluate_pillar(WELT, _ctx({WELT["isin"]: up}, eurusd=eurusd), {})
    assert res["state"] == "hedged" and res["target"] == WELT["hedged"]


def test_bonds_skip_own_instrument_as_fallback():
    down = series([95] + [100] * 12)
    res = S.evaluate_pillar(BONDS, _ctx({BONDS["isin"]: down}), {})
    fb_keys = [r["key"] for r in res["signals"] if r["key"].startswith("fb_")]
    assert fb_keys == ["fb_LU1407888137"]


def test_not_enough_months():
    res = S.evaluate_pillar(GOLD, _ctx({GOLD["isin"]: series([1] * 5)}), {})
    assert not res["ready"] and res["status"] == "5 von 13 Monaten"


def test_plan_action_table():
    assert S.plan_action([], None) == "cash"
    assert S.plan_action([], "A") == "buy"
    assert S.plan_action(["A"], "A") == "hold"
    assert S.plan_action(["A"], None) == "sell"
    assert S.plan_action(["A"], "B") == "switch"


def test_pillars_overview_drift():
    ov = S.pillars_overview({"welt": 41020, "gold": 31200, "anleihen": 28000},
                            {"welt": 40000, "gold": 30000, "anleihen": 30000})
    assert not ov["due"] and ov["drift_pp"] == pytest.approx(2.06, abs=0.01)
    ov = S.pillars_overview({"welt": 50000, "gold": 30000, "anleihen": 20000},
                            {"welt": 40000, "gold": 30000, "anleihen": 30000})
    assert ov["due"] and ov["rows"][0]["target_value"] == pytest.approx(40000)


def test_recession_evaluators():
    un = [(S.add_months("2026-09", -i), 4.0) for i in range(12, 0, -1)] + [("2026-09", 4.5)]
    assert S.eval_unemployment(un)["state"] == "warn"
    weeks = [("2025-09-06", 100.0), ("2025-09-13", 100.0), ("2026-09-05", 110.0), ("2026-09-12", 110.0)]
    assert S.eval_claims(weeks, date(2026, 10, 6))["state"] == "warn"
    yc = [("2025-04-30", -0.1), ("2026-09-30", 1.0)]
    r = S.eval_yield_curve(yc, date(2026, 10, 6))
    assert r["state"] == "warn" and "Apr. 2025" in r["value"]


def test_german_formatting():
    assert S.fmt_eur(41020.6, 0) == "41.021 €"
    assert S.fmt_pct(-0.029) == "−2,9 %"
    assert S.month_label("2026-10") == "Okt. 2026"


# --- Depotpositionen nach dem Login erkennen -------------------------------------------------

def test_parse_isins_cleans_user_input():
    assert S.parse_isins(" ie000vaht5t0, JE00BN2CJ301;foo  IE000VAHT5T0\nDE000A0S9GB0") == [
        "IE000VAHT5T0", "JE00BN2CJ301", "DE000A0S9GB0"]
    assert S.parse_isins(None) == []


def test_resolve_isin_own_equivalent_extra_and_unknown():
    # eigene Instrumente der Säulen (auch gesichert und Ausweichziele)
    assert S.resolve_isin("IE00B3YLTY66", PILLARS) == "IE00B3YLTY66"
    assert S.resolve_isin("LU1407888137", PILLARS) == "LU1407888137"
    # gleichwertige Produkte aus dem Katalog
    assert S.resolve_isin("IE000VAHT5T0", PILLARS) == "IE00B3YLTY66"  # Vanguard FTSE Global All-Cap
    assert S.resolve_isin("JE00BN2CJ301", PILLARS) == "DE000A0S9GB0"  # WisdomTree Core Physical Gold
    assert S.resolve_isin("IE00B441G979", PILLARS) == "IE00BF1B7389"  # MSCI World EUR Hedged
    assert S.resolve_isin("IE00BH04GL39", PILLARS) == "LU0290355717"  # Vanguard Eurozone Gov Bond
    # eigene Zusatz-ISIN zählt wie das eigene Instrument der Säule
    assert S.resolve_isin("IE00BKM4GZ66", PILLARS, {"welt": ["IE00BKM4GZ66"]}) == "IE00B3YLTY66"
    assert S.resolve_isin("US0378331005", PILLARS) is None


def test_held_equivalent_counts_as_target_no_switch():
    held = [S.resolve_isin("IE000VAHT5T0", PILLARS)]
    assert S.plan_action(held, "IE00B3YLTY66") == "hold"
    assert S.plan_action(held, "IE00BF1B7389") == "switch"  # Dollar fällt: gesicherte Klasse


def test_suggest_pillar_for_unknown_positions():
    assert S.suggest_pillar("Physical Gold USD", ["invesco"]) == "gold"
    assert S.suggest_pillar("iShares Gold Producers") is None
    assert S.suggest_pillar("Core Euro Gov Bond EUR (Dist)", ["governmentbonds"]) == "anleihen"
    assert S.suggest_pillar("MSCI World USD (Acc)") == "welt"
    assert S.suggest_pillar("Apple Inc.") is None


def test_tr_split_against_the_decision():
    values = {"welt": 41_000.0, "gold": 31_000.0, "anleihen": 0.0}
    split = S.tr_split(values, {"welt": "IE00B3YLTY66", "gold": "DE000A0S9GB0", "anleihen": None},
                       {"welt": 0.4, "gold": 0.3, "anleihen": 0.3}, cash=28_000.0, unassigned_value=500.0)
    assert split["base"] == 100_000.0
    rows = {r["key"]: r for r in split["rows"]}
    assert rows["welt"]["ist"] == pytest.approx(0.41) and rows["welt"]["soll"] == 0.4
    assert rows["anleihen"]["soll"] == 0.0  # Ziel Cash: keine Wertpapiere
    assert split["cash"]["ist"] == pytest.approx(0.28) and split["cash"]["soll"] == pytest.approx(0.3)
    assert split["unassigned_value"] == 500.0


def test_tr_split_shows_each_product_of_a_pillar():
    parts = {"welt": [{"isin": "IE00B3YLTY66", "name": "SPYI", "value": 20_000.0},
                      {"isin": "IE000VAHT5T0", "name": "Vanguard", "value": 20_000.0}]}
    split = S.tr_split({"welt": 40_000.0}, {"welt": "IE00B3YLTY66"}, {"welt": 1.0}, cash=60_000.0, parts=parts)
    row = split["rows"][0]
    assert row["ist"] == pytest.approx(0.4)
    assert [p["ist"] for p in row["parts"]] == [pytest.approx(0.2), pytest.approx(0.2)]
