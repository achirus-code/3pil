# 🏛️ Säulenwächter

Home-Assistant-**App** (früher „Add-on“) für die **3-Säulen-Strategie** (Welt 40 % · Gold 30 % ·
Euro-Anleihen 30 %, Backtest-Variante „C7“, siehe [docs/3-saeulen-strategie.md](docs/3-saeulen-strategie.md)).

Der Säulenwächter rechnet die komplette Monatslogik selbst nach – Trendsignale, Rezessionszeichen,
Dollar-Signal, Ausweich-Anleihen, Umschaltkurse, Säulen-Drift – zeigt alles in einer eigenen Oberfläche in der
Seitenleiste und als Entitäten in Home Assistant an und meldet **jede neue Erkenntnis per WhatsApp** (CallMeBot)
mit einer konkreten Anweisung. Er **handelt nie selbst**.

## Installation

1. *Einstellungen › Apps › App-Store › ⋮ › Repositories* → `https://github.com/achirus-code/3pil` hinzufügen.
2. **Säulenwächter** installieren. Der Supervisor baut das Image dabei auf deinem Gerät (amd64 oder aarch64,
   dauert beim ersten Mal ein paar Minuten).
3. Im Reiter **Konfiguration** Gesamtbetrag, WhatsApp-Nummer (z. B. `4917…`) und CallMeBot-API-Key eintragen,
   dann **Starten**. „In Seitenleiste anzeigen“ einschalten.
4. In der Oberfläche (Seitenleiste „Säulenwächter“) unten **Bei Trade Republic anmelden**: Telefonnummer und PIN,
   danach in der TR-App bestätigen oder den Authenticator-Code eingeben. Gespeichert wird **nur die Web-Session**
   (in `/data` der App), nie die PIN. Ohne Login rechnet der Säulenwächter mit einem Papierdepot.

Updates kommen über den App-Store von Home Assistant, sobald hier eine neue Version veröffentlicht ist.

**Umstieg von der früheren HACS-Integration:** die Integration unter *Geräte & Dienste* löschen, in HACS
entfernen und Home Assistant neu starten. Danach die App installieren und einmal bei Trade Republic anmelden.
Die Entitäts-IDs sind gleich geblieben, Automationen laufen weiter. Die Lovelace-Karte
`custom:saeulenwaechter-card` gibt es nicht mehr, die Oberfläche liegt jetzt in der Seitenleiste.

## Was angezeigt wird

**Depot erkennen (mit Login):** Die Positionen bei Trade Republic werden anhand der ISIN den Säulen zugeordnet.
Gleichwertige Produkte zählen automatisch wie das Säulen-Instrument und lösen keinen Wechsel aus, z. B.
Vanguard FTSE Global All-Cap / FTSE All-World, iShares Core MSCI World und MSCI ACWI (Welt), WisdomTree Core
Physical Gold, EUWAX Gold II, iShares und Invesco Physical Gold (Gold), iShares und Vanguard
Euro-Staatsanleihen (Anleihen). Weitere ISINs lassen sich in den Optionen je Säule eintragen. Positionen, die zu
keiner Säule passen, zeigt die Karte als „nicht zugeordnet“ (mit Vorschlag) und meldet sie einmal per WhatsApp.

**Handlung nötig (ganz oben, rot):** Weicht das Depot von der Strategie ab (kaufen, verkaufen, wechseln) oder
ist Angleichen fällig, steht ganz oben ein roter, pulsierender Kasten mit der genauen Anweisung je Säule. Er
verschwindet, sobald das Depot zum Ziel passt.

**Säulenstatistik:** Gesamtwert, Einstand und Gewinn/Verlust aller Säulen, darunter je Säule
Wert, Einstand und Gewinn/Verlust der offenen Position (Säulen in Cash ohne Gewinn/Verlust). Darunter der
Verlauf des Gesamtwerts, einmal täglich aufgezeichnet (bis zu zwei Jahre).

**Verteilung bei Trade Republic:** Unter jedem Säulen-Balken zeigt ein zweiter, lila Balken den Anteil im
TR-Depot (erkannte Positionen + Cash) mit dem Soll laut aktueller Entscheidung als Strich, dazu eine Cash-Zeile.
Hält eine Säule mehrere Produkte (z. B. zwei Welt-ETFs), ist der Balken je Produkt farbig unterteilt.

**Entitäten** (je Säule `welt`, `gold`, `anleihen`):

| Entität | Inhalt |
|---|---|
| `sensor.saeulenwaechter_<säule>_zustand` | Investiert / Gesichert / Ausgewichen / Cash, Attribute: alle Signalzeilen, Historie, Ziel |
| `sensor.saeulenwaechter_<säule>_aktion` | halten / kaufen / verkaufen / wechseln (Depot vs. Ziel) |
| `sensor.saeulenwaechter_<säule>_wert`, `_ist_anteil` | Wert zum Geldkurs, Ist-% (Attribut Soll-%) |
| `sensor.saeulenwaechter_<säule>_umschaltkurs`, `_kurs` | Monatsschluss, bei dem das Signal kippt; aktueller Kurs |
| `binary_sensor.saeulenwaechter_<säule>_trend` / `_wuerde_kippen` | Trend an/aus; würde zum Monatsende kippen |
| `sensor.saeulenwaechter_depotwert`, `_gewinn_verlust`, `_drift`, `_naechste_pruefung`, `_euro_zins`, `_dollar`, `_modus` | Übersicht |
| `binary_sensor.saeulenwaechter_rezession_{unemployment,claims,yield_curve}` | Rezessionszeichen |
| `binary_sensor.saeulenwaechter_angleichung_faellig`, `_handlung_noetig`, `_trade_republic` | Drift ≥ 5 Pp; Depot weicht ab (Attribut: Anweisungen); Login-Status |

Die App schreibt die Entitäten über die Home-Assistant-API und erneuert sie jede Minute (nach einem Neustart von
Home Assistant sind sie spätestens nach einer Minute wieder da). Aktualisieren, Angleichen und die
WhatsApp-Testnachricht gibt es als Knöpfe in der Oberfläche.

## Wann kommt eine WhatsApp?

| Erkenntnis | Beispiel |
|---|---|
| Monatsentscheidung (erster Handelstag, LSX offen) | „📅 Monatsentscheidung Nov. 2026 – Welt: Trend abwärts – Rezessionszeichen: US-Zinskurve ➜ WECHSELN: SPDR … komplett verkaufen, danach den Erlös in … anlegen“ |
| Depotposition keiner Säule zugeordnet (mit Login) | „🔎 Depotposition nicht zugeordnet: … – vermutlich Gold“ (einmal je ISIN) |
| Depot weicht vom Ziel ab (mit Login) | „🛠 Gold: KAUFEN: Xetra-Gold für ca. 30.000 €“ – und „✅ umgesetzt“, sobald es im Depot liegt |
| Signal würde zum Monatsende kippen (letzte 7 Tage) | „👀 Welt: Trend würde kippen – heute 10,10 € unter Umschaltkurs 10,17 €“ |
| Rezessionszeichen wechselt | „⚠️ US-Erstanträge warnt jetzt …“ |
| Angleichen fällig (≥ 5 Pp) bzw. jährlich (Monat einstellbar) | „⚖️ Welt 50.000 € → 40.000 € …“ |
| Trade-Republic-Login abgelaufen | „🔑 bitte in der Säulenwächter-App neu anmelden“ |

Jede Erkenntnis wird genau einmal gemeldet; mehrere gleichzeitige werden zu einer Nachricht zusammengefasst.

## Datenquellen

| Daten | Quelle | Login |
|---|---|---|
| Tageskerzen (≈ 5 J.), Kurs, Name | TR-WebSocket `aggregateHistoryLight`, `ticker`, `instrument` (LSX) | nein |
| Depot, Cash | TR-WebSocket `compactPortfolioByType`, `cash` | ja |
| Euribor 3M, EUR/USD | EZB Data API | nein |
| US-Arbeitslosenquote | BLS `LNS14000000` (v2, Rückfall v1; optionaler API-Key) | nein |
| US-Erstanträge (NSA) | DOL-Reihe über FRED `ICNSA` | nein |
| US-Zinskurve 10 J. − 3 M. | US Treasury Daily Rates (CSV) | nein |

Wirtschaftsdaten werden einmal täglich geladen, bei Fehlern nach 2 h neu versucht, der letzte gute Stand gilt 40 Tage.

## Hinweise / Annahmen

- Die Trade-Republic-API ist **inoffiziell** (Login-Ablauf wie `pytr`, Web-Login v2). Sie kann sich jederzeit
  ändern. Der Säulenwächter **handelt nie selbst** – er liest nur und gibt Anweisungen.
- Erstanträge kommen über FRED statt direkt über DOL `ar539` (gleiche DOL-Daten; `ar539.csv` war beim Test nicht
  erreichbar).
- Arbeitslosenquote: „Mittel der 12 Monate bis dahin“ ist inklusive des letzten Werts gerechnet.
- Liegt ein Instrument in mehreren Säulen (z. B. XGLE als Anleihen-Säule **und** als Ausweichziel der Welt),
  wird die Position nach den Soll-Beträgen aufgeteilt.
- Keine Anlageberatung.

## Entwicklung

```text
repository.yaml            App-Repository für Home Assistant
saeulenwaechter/           die App: config.yaml, build.yaml, Dockerfile, DOCS.md, CHANGELOG.md
saeulenwaechter/app/       Python-Dienst: engine.py (Logik), web.py (Ingress-Oberfläche), ha.py (Entitäten)
tests/                     Tests ohne Home Assistant
```

```bash
pip install -r saeulenwaechter/requirements.txt pytest pytest-asyncio pytest-aiohttp
python -m pytest tests
# lokal starten (ohne Home Assistant, Daten in ./data, Oberfläche auf http://127.0.0.1:8099)
cd saeulenwaechter && SW_DATA_DIR=../data SW_ALLOW_ALL=1 python -m app
```

Neue Version: `version` in `saeulenwaechter/config.yaml` und `VERSION` in `app/const.py` erhöhen, Eintrag in
`CHANGELOG.md`, nach `main` mergen. Home Assistant bietet das Update dann an.
