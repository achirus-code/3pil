# Die 3-Säulen-Strategie – vollständige Logik und Darstellung


---

## 1. Das Prinzip

Das Depot besteht aus drei Anlagen, die sich kaum gemeinsam bewegen: **Weltaktien 40 %**, **Gold 30 %** und
**Euro-Staatsanleihen 30 %**. Jede dieser Säulen ist ein eigener Bot mit der Strategie „Monatlicher Trendfolger“.

- **Einmal im Monat** (am ersten Handelstag) entscheidet jede Säule mit den **Monatsschlusskursen**. Es gibt nur
  **ganz drin oder ganz draußen**, keine Teilpositionen.
- **Draußen** liegt das Geld in Cash. Alternativ geht es in die Anleihe mit der besten 12-Monats-Rendite, aber nur,
  wenn diese den Euro-Zins schlägt.
- Die **Welt-Säule** verkauft bei fallendem Trend nur, wenn zusätzlich ein **US-Rezessionszeichen** da ist. Fällt
  der Dollar, hält sie die **währungsgesicherte** Anteilsklasse.
- **Einmal im Jahr** (oder ab 5 Prozentpunkten Abweichung) werden die Beträge wieder auf 40/30/30 gesetzt.

Zwischen zwei Monatsentscheidungen passiert nichts. Kurse innerhalb des Monats verschieben nur die angezeigten
„Umschaltkurse“, also die Information, bei welchem Monatsschluss das Signal kippen würde.

---

## 2. Die Einstellung der drei Säulen (Backtest-Variante „C7“)

| | Welt | Gold | Anleihen |
|---|---|---|---|
| Soll-Anteil (= Betrag) | 40 % | 30 % | 30 % |
| Signal-Instrument | SPYI, IE00B3YLTY66 (MSCI ACWI IMI), alternativ EUNL IE00B4L5Y983 | Xetra-Gold 4GLD, DE000A0S9GB0 | XGLE, LU0290355717 |
| Trendsignal | `either` = Kurs über dem 10-Monats-Ø (Puffer 2 %) **oder** 12-Monats-Rendite > Euro-Zins | `momentum` = 12-Monats-Rendite > Euro-Zins | `momentum` |
| Rezessionszeichen | Arbeitslosigkeit, Erstanträge, Zinskurve: **alle an** | aus | aus |
| Währungsgesichert | IE00BF1B7389 (MSCI ACWI EUR Hedged) | **nein**, wegen der Steuerfreiheit nach einem Jahr | – |
| Ausweichen statt Cash | LU0290355717, LU1407888137 | LU0290355717, LU1407888137 | effektiv nur LU1407888137, weil das eigene Instrument übersprungen wird |
| Zins aus dem Euribor | an | an | an |
| Erlös wieder anlegen | an | an | an |

Die Standardwerte der Parameter sind: Durchschnitt über 10 Monate, Puffer 2 %, Rendite über 12 Monate, fester Zins
2 % p. a. (gilt nur, wenn Euribor-Daten fehlen).

Seit dem 5. Oktober 2026 läuft das Setup im Papiermodus mit 100.000 € (SPYI / 4GLD / XGLE).

---

## 3. Die Monatsentscheidung

### 3.1 Zeitpunkt

- Die Engine prüft nur, solange der Handelsplatz offen ist (LSX, Mo–Fr 07:30–23:00 Europe/Berlin). Der **erste
  Durchlauf in einem neuen UTC-Kalendermonat** fällt deshalb auf den ersten Handelstag.
- Neu entschieden wird, wenn der gespeicherte Monat nicht der aktuelle ist **oder** sich die Signatur der Einstellungen
  geändert hat. Die Signatur besteht aus `signal, sma_months, sma_buffer, momentum_months, cash_rate, cash_rate_auto,
  unemployment, claims, yield_curve, hedged_symbol, fallback_symbols, amount`.
- Die Entscheidung gilt dann für den ganzen Monat. Danach wird nur noch ausgeführt, also Kauf oder Verkauf wiederholt,
  bis die Order durchgeht. „Nächste Prüfung“ ist immer der Erste des Folgemonats.

### 3.2 Monatsschlusskurse

Grundlage sind die Tageskerzen von Trade Republic (`aggregateHistoryLight`, Range `max`, das sind etwa 5 Jahre). Je
**abgeschlossenem** Monat wird der Schlusskurs des letzten Handelstags genommen, neuester zuerst. Die Reihe bricht beim
ersten Monat ohne Kerze ab, damit Lücken keine Monate vertauschen.

Benötigt werden `need = max(sma_months, momentum_months + 1)` Monate, bei `either` also 13. Fehlen welche, lautet der
Status „x von y Monaten“, und es wird nicht gehandelt.

Notation: `c[0]` ist der letzte Monatsschluss, `c[k]` der Schluss vor k Monaten.

### 3.3 Trendsignal A: Kurs über dem Durchschnitt (`sma`)

```
n = 10, b = 0,02
avg = (c[0] + … + c[n−1]) / n
c[0] > avg·(1+b)  → an
c[0] < avg·(1−b)  → aus
sonst             → Zustand vom Vormonat (sma_on), bei einem neuen Bot: aus
```

Der **Umschaltkurs** ist der Monatsschluss, der nächsten Monat das Signal dreht. Dabei ist `rest = c[0] + … + c[n−2]`,
der älteste Wert fällt heraus:

```
wenn an:  aus unter  rest·(1−b) / (n−1+b)
wenn aus: an über    rest·(1+b) / (n−1−b)
```

### 3.4 Trendsignal B: Rendite besser als der Zins (`momentum`)

```
n = 12
ret    = c[0] / c[n] − 1
hurdle = Ertrag von Cash in denselben n Monaten:
         Euribor 3M (EZB, Monatsdurchschnitte):  Π (1 + max(r_i, 0)/100/12) − 1
         ohne Daten oder „Zins aus Euribor“ aus:  cash_rate · n / 12
an  ⇔  ret > hurdle
Umschaltkurs (nächster Monat):  c[n−1] · (1 + hurdle)
```

### 3.5 `either` (Welt-Säule)

`trend_on = sma_on ODER mom_on`. Der Trend gilt erst als gebrochen, wenn der Kurs unter dem Durchschnitt liegt **und**
die Rendite den Zins nicht schlägt.

### 3.6 Rezessionszeichen

Sie werden jeden Monat geladen und angezeigt, **entscheiden aber nur, wenn der Trend aus ist**.

| Zeichen | Quelle | Warnung, wenn … |
|---|---|---|
| US-Arbeitslosenquote | BLS-API v2, Serie `LNS14000000` (saisonbereinigt, monatlich) | letzte Quote > Mittel der 12 Monate bis dahin (mindestens 9 Werte) |
| US-Erstanträge | DOL `ar539` (wöchentlich, nicht saisonbereinigt) | Ø der Wochen des letzten vollständigen Monats mehr als 5 % über dem Vorjahresmonat |
| US-Zinskurve | US Treasury, Daily Treasury Rates (CSV) | 10 J. − 3 M. war an einem der letzten 24 Monatsenden negativ |

```
Trend an                                  → investiert
Trend aus + mindestens ein Zeichen warnt  → raus
Trend aus + alle Zeichen mit Daten ruhig  → bleibt investiert („aber kein Rezessionszeichen … – bleibt investiert“)
Trend aus + zu keinem Zeichen Daten       → raus (der Trend allein entscheidet)
```

Alle Wirtschaftsdaten werden einmal täglich geladen. Fällt eine Quelle aus, gilt der letzte gute Stand bis zu
40 Tage lang, ein neuer Versuch folgt nach 2 Stunden.

### 3.7 Anteilsklasse (nur wenn „Währungsgesicherte Variante“ gesetzt ist)

Grundlage ist EUR/USD zum Monatsende (EZB `EXR/M.USD.EUR.SP00.E`).

- Liegt der Kurs **über seinem 12-Monats-Ø**, steigt der Euro und der Dollar fällt. Ziel ist dann die
  **gesicherte** Variante.
- Andernfalls ist das Ziel das eigene, ungesicherte Instrument.
- Ohne Daten bleibt die bisherige Klasse.
- Das **Signal rechnet immer mit dem eigenen Instrument.**

### 3.8 Ausweichen statt Cash (nur wenn gesetzt)

Möglich sind bis zu drei ISINs, das eigene Instrument wird übersprungen. Für jede wird die 12-Monats-Rendite aus
Monatsschlüssen berechnet (mindestens 13 Monate nötig). Gewählt wird **die höchste Rendite, sofern sie die
12-Monats-Hürde schlägt**. Sonst geht das Geld in Cash. Diese Kandidaten werden ebenfalls jeden Monat angezeigt.

### 3.9 Ziel, Zustand, Ausführung

```
on  → Ziel = gesicherte Variante (Zustand "hedged") oder eigenes Instrument ("in")
off → Ziel = beste Ausweich-Anleihe ("parked") oder nichts ("cash")
```

| gehalten | Ziel | Aktion / Status |
|---|---|---|
| nichts | nichts | „In Cash · {detail} · nächste Prüfung {date}“ |
| nichts | eigenes Instrument | **Kauf**, „Trend aufwärts – kaufe“ |
| nichts | gesicherte Variante | **Kauf**, „Trend aufwärts – kaufe die währungsgesicherte Variante {name}“ |
| nichts | Ausweich-Anleihe | **Kauf**, „Trend abwärts – weiche aus in {name}“ |
| X | X | halten: „Investiert {profit} · …“ / „Investiert in {name} …“ / „Ausgewichen in {name} …“ |
| X | nichts | **ganz verkaufen**, auch mit Verlust: „Trend abwärts – verkaufe“ |
| X | Y | **ganz verkaufen**, „Wechsel zu {name}“, danach beim nächsten Durchlauf Kauf von Y |

- **Kaufbetrag:** Bei „Erlös wieder anlegen“ ist es der Nettoerlös des letzten Verkaufs, sonst der Betrag. Ein
  **geänderter Betrag** (etwa beim Angleichen) verwirft den gemerkten Erlös.
- Kauf und Verkauf laufen als Market-Order mit 1 € Gebühr. Ein Wechsel besteht immer aus Verkauf plus Kauf.
- **Historie:** Je Monat werden `{month, state: in|hedged|parked|cash, name}` gespeichert, höchstens 24 Monate.

---

## 4. Die Säulen-Übersicht (`engine.pillars()`)

Sie gilt für alle **laufenden** Trendfolger desselben Brokers, sobald es mindestens zwei sind.

```
Wert je Säule = offene Position(en) zum Geldkurs (Bid), sonst gemerkter Erlös bzw. Betrag
Soll %        = Betrag / Σ Beträge
Ist %         = Wert / Σ Werte
Drift         = max |Ist − Soll| in Prozentpunkten
fällig        = Drift ≥ 5 Pp
angeglichen   = Soll % · Σ Werte      (neuer Betrag, der den Soll-Anteil wiederherstellt)
```

---

## 5. So sieht die Detailansicht im Bot aus

Die Seite (`BotDetailView`, auf macOS und iPhone gleich aufgebaut) hat diese Reihenfolge: Kopfzeile → Hero-Karte →
Offene Position → **Signale** → **Säulen** → Ergebnis → Parameter → Letzte Trades → Aktivität.

```
┌──────────────────────────────────────────────────────────┐
│ ‹ Zurück              Welt                    Bearbeiten │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │
│ │ [📅]  SPDR MSCI ACWI IMI  [PAPER]          [⏸ Stopp] │ │  Icon calendar.badge.clock,
│ │       Monatlicher Trendfolger · IE00B3YLTY66          │ │  Verlauf grün→blau
│ │ 245,10 €  +0,4 % in 24 h                              │ │
│ │ ● Investiert +1,2 % · Schluss Sep. 2026 … ·           │ │
│ │   nächste Prüfung 2. Nov.                             │ │
│ └──────────────────────────────────────────────────────┘ │
│ OFFENE POSITION                                          │
│  Menge · Einstieg · Investiert · Wert · Ergebnis · Seit  │
│ SIGNALE                                                  │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ✔ Entscheidung Okt. 2026          investiert         │ │
│ │ ✔ Kurs vs. 10-Monats-Ø                               │ │
│ │   Sep. 2026 245,10 € · Ø 227,40 € (+7,8 %)           │ │
│ │   Heute 245,10 € – aus unter 221,80 € (−9,5 %)       │ │
│ │   zum Monatsende                                     │ │
│ │ ✔ 12-Monats-Rendite vs. Zins                         │ │
│ │   +14,0 % vs. +2,2 % (Euribor)                       │ │
│ │   Heute … – aus unter … (…) zum Monatsende           │ │
│ │ ✔ US-Arbeitslosenquote  4,3 % vs. 12-Monats-Ø 4,2 %  │ │
│ │ ✔ US-Erstanträge   −10 % zum Vorjahr (Sep. 2026)     │ │
│ │ ⚠ US-Zinskurve     invers im Apr. 2025 · jetzt … Pp  │ │
│ │ ○ Dollar (EUR/USD) 1,1355 vs. Ø 1,1606 – ungesichert │ │
│ │ ✘ Ausweichen XGLE (12 Monate)  −2,9 % vs. +2,2 %     │ │
│ │ ✘ Ausweichen US-Treasury (12 M.) −6,0 % vs. +2,2 %   │ │
│ │ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■                             │ │
│ │ Okt. 2025 – Okt. 2026  ● Investiert ● Gesichert …    │ │
│ └──────────────────────────────────────────────────────┘ │
│ SÄULEN                                                   │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ **Welt**                                  41 % / 40 %│ │
│ │ ███████████████████░░░░░░░░░|░░░░░░░░░░░░░░░░░░░░░░  │ │
│ │ 41.020 €                                             │ │
│ │ Gold                                      31 % / 30 %│ │
│ │ ██████████████░░░░░░░░░░░░░░░░░░|░░░░░░░░░░░░░░░░░░  │ │
│ │ 31.200 €                                             │ │
│ │ Anleihen                                  28 % / 30 %│ │
│ │ █████████████░░░░░░░░░░░░░░░░░░░|░░░░░░░░░░░░░░░░░░  │ │
│ │ 28.000 €                                             │ │
│ │ Nahe an den Soll-Anteilen (Ist / Soll) – einmal im   │ │
│ │ Jahr angleichen.                                     │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Signalzeilen

Die Reihenfolge ist immer dieselbe:

1. Entscheidung
2. Kurs vs. Ø (bei `sma`/`either`)
3. Rendite vs. Zins (bei `momentum`/`either`)
4. Rezessionszeichen
5. Dollar
6. Ausweich-Kandidaten

Jede Zeile besteht aus Icon (14 pt breit), Titel (11 pt, medium), Wert (10,5 pt, grau) und optional einem Hinweis
(10,5 pt, medium, in der Zustandsfarbe). Ziffern sind monospaced.

| Zustand | Bedeutung | Darstellung |
|---|---|---|
| `on` | Trendsignal an / Entscheidung investiert | ✔ gefüllt, grün |
| `off` | Trendsignal aus / Kandidat schlägt Zins nicht | ✘ rot |
| `ok` | Rezessionszeichen ruhig / Kandidat schlägt Zins / Dollar fällt → gesichert | ✔ Kontur, grün |
| `warn` | Rezessionszeichen warnt | ⚠ orange |
| `neutral` | Dollar steigt → ungesichert | ○ grau |
| `unknown` | keine Daten | ? grau |

**Hinweis (Umschaltkurs):** „Heute {Kurs} – aus unter {Umschaltkurs} ({Abstand}) zum Monatsende“ bzw. „… – an über
…“.

### Monatsstreifen

Je Monat ein abgerundetes Quadrat (12 pt), bis zu 24 Monate:

- grün = investiert
- blau = gesichert
- türkis = in Anleihen ausgewichen
- grau mit 40 % Deckkraft = Cash

Der Tooltip zeigt z. B. „Okt. 2026: Investiert (Name)“. Darunter stehen der Zeitraum und eine Legende, die nur die
vorkommenden Zustände nennt.

### Säulen

- Je Säule:
  - der Name, fett, wenn es die geöffnete Säule ist
  - rechts „Ist % / Soll %“, orange ab 5 Pp Abweichung
  - eine 5 pt hohe Kapsel: Füllung in der Akzentfarbe bis Ist, ein 1,5-pt-Strich bei Soll
  - darunter der Wert in €
- Ist eine Angleichung **fällig**, steht dort „41.020 € → 40.000 €“, dazu der orange Hinweis: „Um x Pp von den
  Soll-Anteilen abgewichen – die Beträge nach dem Pfeil stellen sie wieder her …“.
- Ist sie nicht fällig, steht dort grau: „Nahe an den Soll-Anteilen (Ist / Soll) – einmal im Jahr angleichen.“

---

## 6. Datenquellen auf einen Blick

| Daten | Quelle | Login nötig |
|---|---|---|
| Tageskerzen, Kurs, Instrumentname | TR-WebSocket `aggregateHistoryLight`, `ticker`, `instrument` | **nein** |
| Depotpositionen, Cash | TR-WebSocket `compactPortfolioByType`, `cash`, `availableCash` | **ja** |
| Euribor 3M | EZB `FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA` | nein |
| EUR/USD | EZB `EXR/M.USD.EUR.SP00.E` | nein |
| Arbeitslosenquote | BLS `LNS14000000` | nein |
| Erstanträge | DOL ar539 | nein |
| Zinskurve | US Treasury Daily Rates | nein |

**Folgerung:** Die komplette Strategie, also alle Signale, Entscheidungen und Umschaltkurse, lässt sich **ohne Login**
berechnen. Der Login ist nur nötig, um zu sehen, **was tatsächlich im Depot liegt**.
