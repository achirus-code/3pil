"""Konstanten und die Säulen-Einstellung „C7“ des Säulenwächters."""

from __future__ import annotations

DOMAIN = "saeulenwaechter"
NAME = "Säulenwächter"
VERSION = "1.0.0"

# Config-Entry-Daten
CONF_PHONE = "phone"
CONF_PIN = "pin"
CONF_COOKIES = "cookies"
CONF_DEVICE_ID = "device_id"
CONF_SEC_ACC_NO = "sec_acc_no"
CONF_USE_DEPOT = "use_depot"
CONF_LOGIN_AT = "login_at"

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
