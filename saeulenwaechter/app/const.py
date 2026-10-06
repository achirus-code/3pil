"""Konstanten und die Säulen-Einstellung „C7“ des Säulenwächters."""

from __future__ import annotations

DOMAIN = "saeulenwaechter"
ENTITY_PREFIX = "saeulenwaechter"
NAME = "Säulenwächter"
VERSION = "2.5.1"

# Config-Entry-Daten
CONF_USE_DEPOT = "use_depot"

# Optionen
CONF_TOTAL = "total"
CONF_AMOUNTS = "amounts"
CONF_WA_PHONE = "wa_phone"
CONF_WA_APIKEY = "wa_apikey"
CONF_NOTIFY = "notify"
CONF_MONTHLY_REPORT = "monthly_report"
CONF_SWITCH_WARNING = "switch_warning"
CONF_REBALANCE_MONTH = "rebalance_month"
CONF_BLS_KEY = "bls_key"
CONF_CASH_RATE = "cash_zins"
CONF_CASH_RESERVE = "cash_reserve"
# Eigene Zusatz-ISINs je Säule (zählen wie das eigene Instrument der Säule)
CONF_EXTRA_ISINS = {"welt": "extra_welt", "gold": "extra_gold", "anleihen": "extra_anleihen"}

DEFAULT_TOTAL = 100_000.0
DEFAULT_REBALANCE_MONTH = 1  # Januar

# Handelsplatz
EXCHANGE = "LSX"
TZ = "Europe/Berlin"
MARKET_OPEN = (7, 30)
MARKET_CLOSE = (23, 0)
ORDER_FEE = 1.0

# Säulen-Übersicht
DRIFT_THRESHOLD_PP = 5.0
HISTORY_MONTHS = 24

# Standardparameter des Monatlichen Trendfolgers
SMA_MONTHS = 10
SMA_BUFFER = 0.02
MOMENTUM_MONTHS = 12
CASH_RATE = 0.02  # fester Zins p. a., nur ohne Euribor-Daten

# Ausweich-Anleihen
XGLE = "LU0290355717"
US_TREASURY_EUR = "LU1407888137"

# Die drei Säulen (Backtest-Variante „C7“)
PILLARS: list[dict] = [
    {
        "key": "welt",
        "name": "Welt",
        "weight": 0.40,
        "isin": "IE00B3YLTY66",  # SPDR MSCI ACWI IMI (SPYI)
        "signal": "either",
        "recession": {"unemployment": True, "claims": True, "yield_curve": True},
        "hedged": "IE00BF1B7389",  # MSCI ACWI EUR Hedged
        "fallbacks": [XGLE, US_TREASURY_EUR],
        "cash_rate_auto": True,
        "reinvest": True,
        "color": "#34c759",
    },
    {
        "key": "gold",
        "name": "Gold",
        "weight": 0.30,
        "isin": "DE000A0S9GB0",  # Xetra-Gold (4GLD)
        "signal": "momentum",
        "recession": {"unemployment": False, "claims": False, "yield_curve": False},
        "hedged": None,  # keine Sicherung: Steuerfreiheit nach einem Jahr
        "fallbacks": [XGLE, US_TREASURY_EUR],
        "cash_rate_auto": True,
        "reinvest": True,
        "color": "#ffb300",
    },
    {
        "key": "anleihen",
        "name": "Anleihen",
        "weight": 0.30,
        "isin": XGLE,  # Xtrackers II Eurozone Government Bond (XGLE)
        "signal": "momentum",
        "recession": {"unemployment": False, "claims": False, "yield_curve": False},
        "hedged": None,
        "fallbacks": [XGLE, US_TREASURY_EUR],  # das eigene Instrument wird übersprungen
        "cash_rate_auto": True,
        "reinvest": True,
        "color": "#0a84ff",
    },
]

PILLAR_KEYS = [p["key"] for p in PILLARS]

# Zustände
STATE_IN = "in"
STATE_HEDGED = "hedged"
STATE_PARKED = "parked"
STATE_CASH = "cash"

STATE_LABELS = {
    STATE_IN: "Investiert",
    STATE_HEDGED: "Gesichert",
    STATE_PARKED: "Ausgewichen",
    STATE_CASH: "Cash",
}

MONTHS_DE = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]

# Aktualisierung
UPDATE_INTERVAL_MIN = 15
CANDLE_REFRESH_H = 6
MACRO_REFRESH_H = 24
MACRO_RETRY_H = 2
MACRO_MAX_AGE_DAYS = 40

STORAGE_VERSION = 1
SIGNAL_UPDATE = f"{DOMAIN}_update"

# Gleichwertige Produkte: ISIN im Depot → Säulen-Instrument, für das sie zählt.
# Alle ISINs am 6.10.2026 bei Trade Republic geprüft (Instrumentdaten, handelbar an der LSX).
EQUIVALENTS: dict[str, str] = {
    # Welt – zählen wie SPDR MSCI ACWI IMI
    "IE000VAHT5T0": "IE00B3YLTY66",  # Vanguard FTSE Global All-Cap (Acc)
    "IE000CVUM3N6": "IE00B3YLTY66",  # Vanguard FTSE Global All-Cap (Dist)
    "IE00BK5BQT80": "IE00B3YLTY66",  # Vanguard FTSE All-World (Acc)
    "IE00B3RBWM25": "IE00B3YLTY66",  # Vanguard FTSE All-World (Dist)
    "IE00B6R52259": "IE00B3YLTY66",  # iShares MSCI ACWI (Acc)
    "IE00B4L5Y983": "IE00B3YLTY66",  # iShares Core MSCI World (Acc)
    "IE00BFY0GT14": "IE00B3YLTY66",  # SPDR MSCI World (Acc)
    "IE00BKX55T58": "IE00B3YLTY66",  # Vanguard FTSE Developed World (Dist)
    # Welt gesichert – zählt wie SPDR MSCI ACWI EUR Hedged
    "IE00B441G979": "IE00BF1B7389",  # iShares MSCI World EUR Hedged
    # Gold – zählen wie Xetra-Gold
    "JE00BN2CJ301": "DE000A0S9GB0",  # WisdomTree Core Physical Gold
    "JE00B1VS3770": "DE000A0S9GB0",  # WisdomTree Physical Gold
    "DE000EWG2LD7": "DE000A0S9GB0",  # EUWAX Gold II
    "IE00B4ND3602": "DE000A0S9GB0",  # iShares Physical Gold
    "IE00B579F325": "DE000A0S9GB0",  # Invesco Physical Gold
    # Anleihen – zählen wie Xtrackers Eurozone Government Bond
    "IE00B4WXJJ64": "LU0290355717",  # iShares Core Euro Government Bond
    "IE00BH04GL39": "LU0290355717",  # Vanguard EUR Eurozone Government Bond
}

EQUIVALENT_NAMES: dict[str, str] = {
    "IE000VAHT5T0": "Vanguard FTSE Global All-Cap (Acc)",
    "IE000CVUM3N6": "Vanguard FTSE Global All-Cap (Dist)",
    "IE00BK5BQT80": "Vanguard FTSE All-World (Acc)",
    "IE00B3RBWM25": "Vanguard FTSE All-World (Dist)",
    "IE00B6R52259": "iShares MSCI ACWI",
    "IE00B4L5Y983": "iShares Core MSCI World",
    "IE00BFY0GT14": "SPDR MSCI World",
    "IE00BKX55T58": "Vanguard FTSE Developed World",
    "IE00B441G979": "iShares MSCI World EUR Hedged",
    "JE00BN2CJ301": "WisdomTree Core Physical Gold",
    "JE00B1VS3770": "WisdomTree Physical Gold",
    "DE000EWG2LD7": "EUWAX Gold II",
    "IE00B4ND3602": "iShares Physical Gold",
    "IE00B579F325": "Invesco Physical Gold",
    "IE00B4WXJJ64": "iShares Core Euro Government Bond",
    "IE00BH04GL39": "Vanguard EUR Eurozone Government Bond",
}
