"""Die reine Logik der 3-Säulen-Strategie (Monatlicher Trendfolger).

Dieses Modul hat keine Abhängigkeit zu Home Assistant und lässt sich direkt testen.
Notation wie in docs/3-saeulen-strategie.md: c[0] ist der letzte Monatsschluss,
c[k] der Schluss vor k Monaten.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from .const import (
    CASH_RATE,
    EQUIVALENTS,
    DRIFT_THRESHOLD_PP,
    MOMENTUM_MONTHS,
    MONTHS_DE,
    SMA_BUFFER,
    SMA_MONTHS,
    STATE_CASH,
    STATE_HEDGED,
    STATE_IN,
    STATE_LABELS,
    STATE_PARKED,
)

# ---------------------------------------------------------------------------
# Formatierung (deutsch)
# ---------------------------------------------------------------------------


def _de(num: float, decimals: int) -> str:
    s = f"{num:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_eur(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "–"
    return f"{_de(value, decimals)} €"


def fmt_pct(value: float | None, decimals: int = 1, sign: bool = True) -> str:
    if value is None:
        return "–"
    pct = round(value * 100, decimals)
    if pct == 0:
        pct = 0.0  # kein „−0,0 %“
    txt = _de(abs(pct), decimals)
    if not sign:
        return f"{'−' if pct < 0 else ''}{txt} %"
    return f"{'−' if pct < 0 else '+'}{txt} %"


def fmt_num(value: float | None, decimals: int = 1) -> str:
    return "–" if value is None else _de(value, decimals)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_label(key: str | None) -> str:
    if not key:
        return "–"
    y, m = key.split("-")
    return f"{MONTHS_DE[int(m) - 1]} {y}"


def add_months(key: str, delta: int) -> str:
    y, m = (int(x) for x in key.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def next_check_date(today: date) -> date:
    """„Nächste Prüfung“ ist immer der Erste des Folgemonats."""
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


# ---------------------------------------------------------------------------
# 3.2 Monatsschlusskurse
# ---------------------------------------------------------------------------


def monthly_closes(candles: list[dict], today: date) -> list[tuple[str, float]]:
    """Schlusskurs des letzten Handelstags je abgeschlossenem Monat, neuester zuerst.

    Die Reihe bricht beim ersten Monat ohne Kerze ab, damit Lücken keine Monate vertauschen.
    """
    current = month_key(today)
    last: dict[str, tuple[int, float]] = {}
    for c in candles:
        try:
            t = int(c["time"])
            close = float(c["close"])
        except (KeyError, TypeError, ValueError):
            continue
        key = month_key(datetime.fromtimestamp(t / 1000, tz=timezone.utc).date())
        if key >= current:
            continue
        if key not in last or t > last[key][0]:
            last[key] = (t, close)
    if not last:
        return []
    out: list[tuple[str, float]] = []
    expected = max(last)
    while expected in last:
        out.append((expected, last[expected][1]))
        expected = add_months(expected, -1)
    return out


def needed_months(signal: str) -> int:
    if signal == "sma":
        return SMA_MONTHS
    if signal == "momentum":
        return MOMENTUM_MONTHS + 1
    return max(SMA_MONTHS, MOMENTUM_MONTHS + 1)


# ---------------------------------------------------------------------------
# 3.3 Kurs über dem Durchschnitt
# ---------------------------------------------------------------------------


def sma_signal(closes: list[float], prev_on: bool | None, n: int = SMA_MONTHS, b: float = SMA_BUFFER) -> dict:
    avg = sum(closes[:n]) / n
    c0 = closes[0]
    if c0 > avg * (1 + b):
        on = True
    elif c0 < avg * (1 - b):
        on = False
    else:
        on = bool(prev_on)
    rest = sum(closes[: n - 1])
    if on:
        switch = rest * (1 - b) / (n - 1 + b)
    else:
        switch = rest * (1 + b) / (n - 1 - b)
    return {"on": on, "avg": avg, "close": c0, "diff": c0 / avg - 1, "switch": switch}


# ---------------------------------------------------------------------------
# 3.4 Rendite besser als der Zins
# ---------------------------------------------------------------------------


def hurdle(euribor: dict[str, float] | None, end_month: str, n: int = MOMENTUM_MONTHS,
           cash_rate: float = CASH_RATE, auto: bool = True) -> tuple[float, str]:
    """Ertrag von Cash in den n Monaten bis einschließlich end_month."""
    if auto and euribor:
        months = sorted(k for k in euribor if k <= end_month)[-n:]
        if len(months) == n:
            prod = 1.0
            for m in months:
                prod *= 1 + max(euribor[m], 0.0) / 100 / 12
            return prod - 1, "Euribor"
    return cash_rate * n / 12, "fest"


def momentum_signal(closes: list[float], hurdle_value: float, n: int = MOMENTUM_MONTHS) -> dict:
    ret = closes[0] / closes[n] - 1
    return {
        "on": ret > hurdle_value,
        "ret": ret,
        "hurdle": hurdle_value,
        "switch": closes[n - 1] * (1 + hurdle_value),
    }


def twelve_month_return(closes: list[float], n: int = MOMENTUM_MONTHS) -> float | None:
    if len(closes) < n + 1:
        return None
    return closes[0] / closes[n] - 1


# ---------------------------------------------------------------------------
# 3.6 Rezessionszeichen (Bewertung der geladenen Reihen)
# ---------------------------------------------------------------------------


def eval_unemployment(series: list[tuple[str, float]] | None) -> dict:
    """series: (YYYY-MM, Quote) chronologisch. Warnung: letzte Quote > Mittel der 12 Monate bis dahin."""
    row = {"key": "unemployment", "title": "US-Arbeitslosenquote", "state": "unknown", "value": "keine Daten"}
    if not series:
        return row
    window = [v for _, v in series[-12:]]
    if len(window) < 9:
        return row
    last = window[-1]
    avg = sum(window) / len(window)
    row["state"] = "warn" if last > avg else "ok"
    row["value"] = f"{fmt_num(last)} % vs. 12-Monats-Ø {fmt_num(avg)} % ({month_label(series[-1][0])})"
    row["last"], row["avg"] = last, avg
    return row


def eval_claims(weeks: list[tuple[str, float]] | None, today: date) -> dict:
    """weeks: (YYYY-MM-DD Wochenende, Erstanträge NSA). Ø des letzten vollständigen Monats vs. Vorjahresmonat."""
    row = {"key": "claims", "title": "US-Erstanträge", "state": "unknown", "value": "keine Daten"}
    if not weeks:
        return row
    by_month: dict[str, list[float]] = {}
    for d, v in weeks:
        by_month.setdefault(d[:7], []).append(v)
    current = month_key(today)
    complete = sorted(m for m in by_month if m < current)
    for m in reversed(complete):
        prev = add_months(m, -12)
        if prev in by_month:
            avg = sum(by_month[m]) / len(by_month[m])
            avg_prev = sum(by_month[prev]) / len(by_month[prev])
            change = avg / avg_prev - 1
            row["state"] = "warn" if change > 0.05 else "ok"
            row["value"] = f"{fmt_pct(change, 0)} zum Vorjahr ({month_label(m)})"
            row["change"] = change
            return row
    return row


def eval_yield_curve(daily: list[tuple[str, float]] | None, today: date, months: int = 24) -> dict:
    """daily: (YYYY-MM-DD, 10 J. − 3 M. in Pp). Warnung, wenn an einem der letzten 24 Monatsenden negativ."""
    row = {"key": "yield_curve", "title": "US-Zinskurve", "state": "unknown", "value": "keine Daten"}
    if not daily:
        return row
    month_end: dict[str, tuple[str, float]] = {}
    for d, spread in sorted(daily):
        month_end[d[:7]] = (d, spread)
    current = month_key(today)
    ends = sorted(m for m in month_end if m < current)[-months:]
    if not ends:
        return row
    now_spread = sorted(daily)[-1][1]
    inverted = [m for m in ends if month_end[m][1] < 0]
    if inverted:
        row["state"] = "warn"
        row["value"] = f"invers im {month_label(inverted[-1])} · jetzt {_signed(now_spread)} Pp"
    else:
        row["state"] = "ok"
        row["value"] = f"nicht invers ({len(ends)} Monatsenden) · jetzt {_signed(now_spread)} Pp"
    row["spread"] = now_spread
    return row


def _signed(v: float) -> str:
    return f"{'−' if v < 0 else '+'}{_de(abs(v), 2)}"


# ---------------------------------------------------------------------------
# 3.7 Anteilsklasse
# ---------------------------------------------------------------------------


def eval_dollar(eurusd: dict[str, float] | None, end_month: str) -> dict:
    row = {"key": "dollar", "title": "Dollar (EUR/USD)", "state": "unknown", "value": "keine Daten", "hedge": None}
    if not eurusd:
        return row
    months = sorted(k for k in eurusd if k <= end_month)[-12:]
    if len(months) < 12:
        return row
    last = eurusd[months[-1]]
    avg = sum(eurusd[m] for m in months) / 12
    hedge = last > avg  # Euro steigt, Dollar fällt → gesichert
    row["hedge"] = hedge
    row["state"] = "ok" if hedge else "neutral"
    row["value"] = f"{fmt_num(last, 4)} vs. Ø {fmt_num(avg, 4)} – {'gesichert' if hedge else 'ungesichert'}"
    return row


# ---------------------------------------------------------------------------
# Auswertung einer Säule
# ---------------------------------------------------------------------------


def evaluate_pillar(cfg: dict, ctx: dict, prev: dict | None) -> dict:
    """Wertet eine Säule mit den aktuellen Monatsschlüssen aus.

    ctx: closes{isin: [(month, close)]}, euribor{month: %}, eurusd{month: kurs},
         macro{key: row}, names{isin: name}, symbols{isin: kürzel}, prices{isin: {bid, ask, last}}, today
    prev: gespeicherter Zustand der Säule (sma_on, state, …)
    """
    prev = prev or {}
    today: date = ctx["today"]
    own = cfg["isin"]
    signal = cfg["signal"]
    series = ctx["closes"].get(own) or []
    closes = [c for _, c in series]
    need = needed_months(signal)
    names = ctx.get("names", {})
    symbols = ctx.get("symbols", {})
    price_now = (ctx.get("prices", {}).get(own) or {}).get("last")

    res: dict[str, Any] = {
        "key": cfg["key"],
        "ready": len(closes) >= need,
        "months_have": min(len(closes), need),
        "months_need": need,
        "close_month": series[0][0] if series else None,
        "close": closes[0] if closes else None,
        "price": price_now,
        "signals": [],
    }
    if not res["ready"]:
        res["status"] = f"{len(closes)} von {need} Monaten"
        return res

    m0 = series[0][0]
    hurdle_value, hurdle_src = hurdle(ctx.get("euribor"), m0, auto=cfg.get("cash_rate_auto", True))
    res["hurdle"], res["hurdle_source"] = hurdle_value, hurdle_src

    sma = mom = None
    if signal in ("sma", "either"):
        # Die Hysterese nutzt den Zustand des Vormonats (bei einem neuen Bot: aus)
        sma = sma_signal(closes, prev.get("sma_on_prev") if prev.get("month") == month_key(today)
                         else prev.get("sma_on"))
        res["sma"] = sma
    if signal in ("momentum", "either"):
        mom = momentum_signal(closes, hurdle_value)
        res["mom"] = mom

    if signal == "sma":
        trend_on = sma["on"]
    elif signal == "momentum":
        trend_on = mom["on"]
    else:
        trend_on = sma["on"] or mom["on"]
    res["trend_on"] = trend_on

    # Rezessionszeichen
    macro = ctx.get("macro", {})
    rec_rows = [macro.get(k) or {"key": k, "state": "unknown"} for k, on in cfg["recession"].items() if on]
    recession_reason = ""
    if trend_on:
        invested = True
    elif not rec_rows:
        invested = False
    else:
        with_data = [r for r in rec_rows if r.get("state") in ("ok", "warn")]
        warns = [r for r in with_data if r["state"] == "warn"]
        if not with_data:
            invested = False
            recession_reason = "keine Rezessionsdaten – der Trend allein entscheidet"
        elif warns:
            invested = False
            recession_reason = "Rezessionszeichen: " + ", ".join(r.get("title", r["key"]) for r in warns)
        else:
            invested = True
            recession_reason = "aber kein Rezessionszeichen – bleibt investiert"
    res["invested"] = invested
    res["recession_reason"] = recession_reason

    # Anteilsklasse
    dollar = None
    hedge = False
    if cfg.get("hedged"):
        dollar = eval_dollar(ctx.get("eurusd"), m0)
        if dollar["hedge"] is None:
            hedge = prev.get("state") == STATE_HEDGED
        else:
            hedge = dollar["hedge"]

    # Ausweichen statt Cash
    fb_rows = []
    best = None
    for isin in cfg.get("fallbacks", [])[:3]:
        if isin == own:
            continue
        fb_closes = [c for _, c in (ctx["closes"].get(isin) or [])]
        ret = twelve_month_return(fb_closes)
        label = symbols.get(isin) or names.get(isin) or isin
        if ret is None:
            fb_rows.append({"key": f"fb_{isin}", "state": "unknown", "title": f"Ausweichen {label} (12 Monate)",
                            "value": "zu wenig Monate", "isin": isin})
            continue
        beats = ret > hurdle_value
        fb_rows.append({"key": f"fb_{isin}", "state": "ok" if beats else "off",
                        "title": f"Ausweichen {label} (12 Monate)",
                        "value": f"{fmt_pct(ret)} vs. {fmt_pct(hurdle_value)}", "isin": isin, "ret": ret})
        if beats and (best is None or ret > best[1]):
            best = (isin, ret)

    # Ziel und Zustand (3.9)
    if invested:
        if hedge and cfg.get("hedged"):
            target, state = cfg["hedged"], STATE_HEDGED
        else:
            target, state = own, STATE_IN
    elif best:
        target, state = best[0], STATE_PARKED
    else:
        target, state = None, STATE_CASH
    res["target"] = target
    res["target_name"] = names.get(target) if target else None
    res["state"] = state

    # Signalzeilen in fester Reihenfolge
    rows: list[dict] = []
    rows.append({"key": "decision", "state": "on" if invested else "off",
                 "title": f"Entscheidung {month_label(month_key(today))}",
                 "value": STATE_LABELS[state].lower() if state != STATE_CASH else "Cash",
                 "hint": recession_reason or None})
    if sma:
        hint = _switch_hint(price_now, sma["switch"], sma["on"])
        rows.append({"key": "sma", "state": "on" if sma["on"] else "off",
                     "title": f"Kurs vs. {SMA_MONTHS}-Monats-Ø",
                     "value": f"{month_label(m0)} {fmt_eur(sma['close'])} · Ø {fmt_eur(sma['avg'])} ({fmt_pct(sma['diff'])})",
                     "hint": hint, "switch": sma["switch"]})
    if mom:
        hint = _switch_hint(price_now, mom["switch"], mom["on"])
        rows.append({"key": "mom", "state": "on" if mom["on"] else "off",
                     "title": f"{MOMENTUM_MONTHS}-Monats-Rendite vs. Zins",
                     "value": f"{fmt_pct(mom['ret'])} vs. {fmt_pct(hurdle_value)} ({hurdle_src})",
                     "hint": hint, "switch": mom["switch"]})
    for r in rec_rows:
        rows.append({k: r.get(k) for k in ("key", "state", "title", "value")})
    if dollar:
        rows.append({k: dollar.get(k) for k in ("key", "state", "title", "value")})
    rows.extend(fb_rows)
    res["signals"] = rows

    # Maßgeblicher Umschaltkurs: bei „either“ der, der den Trend tatsächlich dreht
    res["switch"] = _effective_switch(signal, sma, mom)
    res["switch_dir"] = "off" if trend_on else "on"
    return res


def _switch_hint(price: float | None, switch: float, on: bool) -> str | None:
    if price is None or not switch:
        return None
    dist = switch / price - 1
    word = "aus unter" if on else "an über"
    return f"Heute {fmt_eur(price)} – {word} {fmt_eur(switch)} ({fmt_pct(dist)}) zum Monatsende"


def _effective_switch(signal: str, sma: dict | None, mom: dict | None) -> float | None:
    if signal == "sma":
        return sma["switch"]
    if signal == "momentum":
        return mom["switch"]
    if sma["on"] or mom["on"]:
        # either: Trend bricht erst, wenn beide aus sind → der niedrigere der aktiven Umschaltkurse
        return min(s["switch"] for s in (sma, mom) if s["on"])
    return min(sma["switch"], mom["switch"])  # an, sobald eines der beiden dreht


def would_flip(res: dict, price: float | None) -> bool:
    """Würde der Trend kippen, wenn der Monat heute zu diesem Kurs schlösse?"""
    sw = res.get("switch")
    if price is None or sw is None or "trend_on" not in res:
        return False
    return price < sw if res["trend_on"] else price > sw


# ---------------------------------------------------------------------------
# 3.9 Ausführung
# ---------------------------------------------------------------------------


def plan_action(held: list[str], target: str | None) -> str:
    """held: ISINs, die die Säule hält. Ergebnis: cash | buy | hold | sell | switch."""
    if not held:
        return "buy" if target else "cash"
    if target is None:
        return "sell"
    if set(held) == {target}:
        return "hold"
    return "switch"


def decision_signature(cfg: dict, amount: float) -> str:
    parts = [cfg["signal"], SMA_MONTHS, SMA_BUFFER, MOMENTUM_MONTHS, CASH_RATE, cfg.get("cash_rate_auto"),
             cfg["recession"]["unemployment"], cfg["recession"]["claims"], cfg["recession"]["yield_curve"],
             cfg.get("hedged"), ",".join(cfg.get("fallbacks", [])), round(amount, 2)]
    return "|".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# 4. Säulen-Übersicht
# ---------------------------------------------------------------------------


def pillars_overview(values: dict[str, float], amounts: dict[str, float]) -> dict:
    total_amount = sum(amounts.values()) or 1.0
    total_value = sum(values.values())
    rows = []
    drift = 0.0
    for key, amount in amounts.items():
        value = values.get(key, 0.0)
        soll = amount / total_amount
        ist = value / total_value if total_value else 0.0
        diff_pp = (ist - soll) * 100
        drift = max(drift, abs(diff_pp))
        rows.append({"key": key, "value": value, "amount": amount, "soll": soll, "ist": ist,
                     "diff_pp": diff_pp, "target_value": soll * total_value})
    due = drift >= DRIFT_THRESHOLD_PP
    return {"rows": rows, "total": total_value, "drift_pp": drift, "due": due}


# ---------------------------------------------------------------------------
# Depotpositionen erkennen (nach dem TR-Login)
# ---------------------------------------------------------------------------

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def parse_isins(text: str | None) -> list[str]:
    """„IE000VAHT5T0, ie00b4l5y983“ → gültige ISINs in Großbuchstaben, ohne Doppelte."""
    out: list[str] = []
    for part in re.split(r"[\s,;]+", text or ""):
        part = part.strip().upper()
        if ISIN_RE.match(part) and part not in out:
            out.append(part)
    return out


def resolve_isin(isin: str, pillars: list[dict], extras: dict[str, list[str]] | None = None) -> str | None:
    """Das Säulen-Instrument, für das eine Depot-ISIN zählt.

    Reihenfolge: ein Instrument der Säulen selbst, ein gleichwertiges Produkt aus dem Katalog,
    eine eigene Zusatz-ISIN (zählt wie das eigene Instrument der Säule). Sonst None.
    """
    for cfg in pillars:
        if isin in (cfg["isin"], cfg.get("hedged"), *cfg.get("fallbacks", [])):
            return isin
    if isin in EQUIVALENTS:
        return EQUIVALENTS[isin]
    for cfg in pillars:
        if isin in (extras or {}).get(cfg["key"], []):
            return cfg["isin"]
    return None


def suggest_pillar(name: str | None, tags: list[str] | None = None) -> str | None:
    """Vorschlag für eine unbekannte Position anhand von Name und TR-Tags (nur als Hinweis)."""
    n = (name or "").lower()
    if "gold" in n and not any(w in n for w in ("miner", "producer", "mining", "explorer", "bergbau")):
        return "gold"
    if "governmentbonds" in (tags or []) or any(w in n for w in ("gov bond", "govt bond", "government bond",
                                                                  "staatsanleihe", "treasury")):
        return "anleihen"
    if any(w in n for w in ("all-world", "all world", "all country", "acwi", "msci world", "developed world",
                            "global all-cap", "global all cap")):
        return "welt"
    return None


def tr_split(pillar_values: dict[str, float], targets: dict[str, str | None], soll: dict[str, float],
             cash: float | None, unassigned_value: float = 0.0,
             parts: dict[str, list[dict]] | None = None) -> dict:
    """Verteilung im TR-Depot (Ist) gegen die Verteilung laut Strategie (Soll).

    Basis = erkannte Säulen-Positionen + Cash. Eine Säule, deren Ziel Cash ist, soll 0 % in Wertpapieren
    halten; ihr Anteil gehört dann zum Soll-Cash.
    """
    cash = max(cash or 0.0, 0.0)
    base = sum(pillar_values.values()) + cash
    rows = []
    for key, value in pillar_values.items():
        target_share = soll.get(key, 0.0) if targets.get(key) else 0.0
        # einzelne Produkte der Säule (z. B. zwei Welt-ETFs) als Teile des Balkens
        segs = [{"isin": h["isin"], "name": h["name"], "value": h["value"],
                 "ist": h["value"] / base if base else 0.0}
                for h in (parts or {}).get(key, []) if h.get("value")]
        rows.append({"key": key, "value": value, "ist": value / base if base else 0.0, "soll": target_share,
                     "parts": segs})
    soll_cash = sum(soll.get(k, 0.0) for k in pillar_values if not targets.get(k))
    return {"base": base, "rows": rows,
            "cash": {"value": cash, "ist": cash / base if base else 0.0, "soll": soll_cash},
            "unassigned_value": unassigned_value}



def pillar_stats(pillars: list[dict]) -> dict:
    """Statistik der Säulen: Wert, Einstand, Gewinn/Verlust je Säule und gesamt.

    pillars: [{key, name, value, held: [{cost, value}]}]. Gewinn/Verlust nur für offene Positionen mit
    bekanntem Einstand und Kurs; eine Säule in Cash zählt mit ihrem Wert, aber ohne Gewinn/Verlust.
    """
    rows = []
    for p in pillars:
        held = p.get("held") or []
        known = held and all(h.get("cost") and h.get("value") is not None for h in held)
        cost = sum(h["cost"] for h in held) if known else None
        pos_value = sum(h["value"] for h in held) if known else None
        pnl = pos_value - cost if known else None
        rows.append({"key": p["key"], "name": p["name"], "value": p.get("value"), "cost": cost,
                     "pnl": pnl, "pnl_pct": pnl / cost if known and cost else None, "invested": bool(held)})
    with_pnl = [r for r in rows if r["pnl"] is not None]
    cost = sum(r["cost"] for r in with_pnl)
    pnl = sum(r["pnl"] for r in with_pnl)
    return {"rows": rows, "total": {"value": sum(r["value"] or 0 for r in rows), "cost": cost if with_pnl else None,
                                    "pnl": pnl if with_pnl else None, "pnl_pct": pnl / cost if cost else None}}
