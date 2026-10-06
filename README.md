# 🏛️ Säulenwächter

Home-Assistant-Integration für die **3-Säulen-Strategie** (Welt 40 % · Gold 30 % · Euro-Anleihen 30 %,
Backtest-Variante „C7“, siehe [docs/3-saeulen-strategie.md](docs/3-saeulen-strategie.md)).

Der Säulenwächter rechnet die komplette Monatslogik selbst nach – Trendsignale, Rezessionszeichen,
Dollar-Signal, Ausweich-Anleihen, Umschaltkurse, Säulen-Drift – zeigt alles als Entitäten, Lovelace-Karte und
eigenes Seitenleisten-Panel an und meldet **jede neue Erkenntnis per WhatsApp** (CallMeBot) mit einer konkreten
Anweisung.

## Installation

1. **HACS:** *HACS › ⋮ › Benutzerdefinierte Repositories* → `https://github.com/achirus-code/3pil`, Typ
   „Integration“ → „Säulenwächter“ herunterladen.
   **Manuell:** `saeulenwaechter.zip` aus dem [neuesten Release](https://github.com/achirus-code/3pil/releases/latest)
   nach `<HA-config>/custom_components/saeulenwaechter/` entpacken.
2. Home Assistant neu starten.
3. *Einstellungen › Geräte & Dienste › Integration hinzufügen › Säulenwächter*.
   - **Mit Trade Republic verbinden (einmalig):** Telefonnummer + PIN, danach die Anmeldung in der TR-App
     bestätigen (oder Authenticator-Code eingeben). Gespeichert wird **nur die Web-Session**, nicht die PIN.
     Die Session wird alle 15 Minuten automatisch verlängert. Läuft sie doch ab, startet HA einen
     „Erneut anmelden“-Dialog und du bekommst eine WhatsApp.
   - **Ohne Login – Papierdepot:** alle Signale + simuliertes Depot (Market-Order, 1 € Gebühr, Erlös wieder anlegen).
4. WhatsApp: Nummer (z. B. `4917…`) und CallMeBot-API-Key eintragen. Mit dem Button
   **„WhatsApp-Testnachricht“** prüfen.

## Was angezeigt wird

**Panel „Säulenwächter“ in der Seitenleiste** und die **Karte** `custom:saeulenwaechter-card`:

```yaml
type: custom:saeulenwaechter-card          # Übersicht aller drei Säulen + Ist/Soll
---
type: custom:saeulenwaechter-card
pillar: welt                               # Detailansicht: Hero, Position, Signale, Monatsstreifen, Säulen
```

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
| `sensor.saeulenwaechter_depotwert`, `_drift`, `_naechste_pruefung`, `_euro_zins`, `_dollar`, `_modus` | Übersicht |
| `binary_sensor.saeulenwaechter_rezession_{unemployment,claims,yield_curve}` | Rezessionszeichen |
| `binary_sensor.saeulenwaechter_angleichung_faellig`, `_trade_republic` | Drift ≥ 5 Pp; Login-Status |
| `button.saeulenwaechter_{aktualisieren,angleichen,testnachricht}` | Aktionen |

Services: `saeulenwaechter.refresh`, `saeulenwaechter.apply_rebalance`, `saeulenwaechter.send_test_message`.

## Wann kommt eine WhatsApp?

| Erkenntnis | Beispiel |
|---|---|
| Monatsentscheidung (erster Handelstag, LSX offen) | „📅 Monatsentscheidung Nov. 2026 – Welt: Trend abwärts – Rezessionszeichen: US-Zinskurve ➜ WECHSELN: SPDR … komplett verkaufen, danach den Erlös in … anlegen“ |
| Depotposition keiner Säule zugeordnet (mit Login) | „🔎 Depotposition nicht zugeordnet: … – vermutlich Gold“ (einmal je ISIN) |
| Depot weicht vom Ziel ab (mit Login) | „🛠 Gold: KAUFEN: Xetra-Gold für ca. 30.000 €“ – und „✅ umgesetzt“, sobald es im Depot liegt |
| Signal würde zum Monatsende kippen (letzte 7 Tage) | „👀 Welt: Trend würde kippen – heute 10,10 € unter Umschaltkurs 10,17 €“ |
| Rezessionszeichen wechselt | „⚠️ US-Erstanträge warnt jetzt …“ |
| Angleichen fällig (≥ 5 Pp) bzw. jährlich (Monat einstellbar) | „⚖️ Welt 50.000 € → 40.000 € …“ |
| Trade-Republic-Login abgelaufen | „🔑 bitte neu anmelden“ |

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

```bash
./scripts/build.sh                # baut dist/saeulenwaechter.zip
```

Ein neues Release (`gh release create vX.Y.Z`) baut das ZIP per GitHub Action automatisch und hängt es an.

```bash
python -m pytest tests            # reine Strategie-Logik (ohne HA)
python -m pytest tests_ha         # Integrationstests in Home Assistant (pytest-homeassistant-custom-component)
```
