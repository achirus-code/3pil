# Changelog

## 2.13.0

- Schneller: Die Wertentwicklung wird erst beim Öffnen des Popups berechnet (im Hintergrund, mit Ladebalken) und zwischengespeichert. Die Seite lädt dadurch nur noch ~15 KB statt ~275 KB pro Aktualisierung.
- Berechnung des Verlaufs deutlich schneller (Käufe/Verkäufe mit Zeiger statt Summe je Tag); Käufe an Tagen ohne Kurs (z. B. Wochenende, physisches Gold) werden korrekt als Zufluss gezählt.

## 2.12.3

- Nach einem Neustart (z. B. Update) sofort Daten aus dem gespeicherten Stand statt „Säulenwächter hat noch keine Daten“; die aktuellen Kurse werden im Hintergrund geladen.

## 2.12.2

- Positionstabelle in der Wertentwicklung sortierbar (Position, Wert, Im Zeitraum, Seit Kauf – Klick auf die Überschrift, erneut für umgekehrt).
- Prozentwerte in Klammern: Anteil am Depot beim Wert, Rendite im Zeitraum und seit Kauf.

## 2.12.1

- Steuern netto: Die beim Verkauf einbehaltene Steuer (Zeile „Steuer“ in den Transaktionsdetails) zählt jetzt als Steuer, Erstattungen und Korrekturen werden gegengerechnet. Vorher enthielt „Steuern“ nur Erstattungen – der Haken „Steuern einrechnen“ erhöhte deshalb den Gewinn. Kursgewinne werden vor Steuern ausgewiesen.

## 2.12.0

- „Seit Beginn“ exakt aus den Buchungen: heutiger Wert bei Trade Republic (Wertpapiere + Cash) − eingezahltes Geld, aufgeteilt in Kursgewinne, Dividenden, Zinsen und Steuern; dazu „ohne Zinsen“ zum Vergleich mit der TR-App. Physisches Gold separat.
- Haken „Zinsen einrechnen“ und „Steuern einrechnen“ in der Wertentwicklung: wirken auf alle Zeiträume, „Seit Beginn“ und den Tooltip; die Wahl bleibt im Browser gespeichert.
- Hinweis, wenn für eine Position kein Kursverlauf vorliegt; „Max.“ heißt jetzt „Alle Kurse“ (reicht nur so weit zurück wie die Tageskurse).

## 2.11.2

- Komplett verkaufte Positionen gehören jetzt in den Verlauf: vor dem Verkauf zählt ihr Wert, ihr Gewinn bis zum Verkauf geht in den Gewinn ein. Vorher erschien nur der Verkaufserlös als Cash – das Depot sah in der Vergangenheit zu klein aus und der Cash-Verlauf wurde verworfen.
- Dafür liest die App alle Käufe/Verkäufe der Zeitleiste und holt Kurse auch für verkaufte Wertpapiere.

## 2.11.1

- Gewinn korrigiert: Gewinn = Wertänderung der Positionen ohne Käufe/Verkäufe plus Dividenden, Zinsen und Steuern. Ein- und Auszahlungen (und Fehler im Cash-Verlauf) können den Gewinn nicht mehr verfälschen – vorher erschienen z. B. +40.884 € als „Zinsen, Dividenden“.
- Geldbewegungen nach Ereignistyp von Trade Republic eingeteilt; ausgeblendete Einträge und doppelte Buchungen (alter/neuer Typ) werden übergangen.
- Cash-Verlauf aus der Zeitleiste nur, wenn er plausibel ist (nie deutlich unter null), sonst Näherung.

## 2.11.0

- Echter Depotwert in der Wertentwicklung: alle Positionen (Säulen und „Sonstige“, z. B. Einzelaktien) plus Cash. Cash je Tag exakt aus allen Geldbewegungen der Trade-Republic-Zeitleiste.
- Gewinn = Wertänderung ohne Ein- und Auszahlungen; Dividenden, Zinsen, Gebühren und Steuern werden separat ausgewiesen.
- Tabelle je Position: Wert, Gewinn im gewählten Zeitraum, Gewinn seit Kauf.
- Tageskurse für alle Depot-Positionen von Trade Republic; fehlen sie oder beginnen sie zu spät, ergänzt die App sie von Yahoo Finance.

## 2.10.3

- Stückzahlen wie „1.500“ (deutscher Tausenderpunkt) wurden als 1,5 gelesen – dadurch fehlten Stücke in der Historie. Behoben.
- „Failed to fetch“: Bei einem kurzen Verbindungsabbruch (z. B. Neustart von Home Assistant) bleiben die letzten Daten stehen und die Seite versucht es nach wenigen Sekunden erneut.

## 2.10.2

- Stückzahl aus den Transaktionsdetails im aktuellen Format „Transaktion: 2.805,927158 × 11,51 €“ – vorher wurde sie fast nie gefunden und nur geschätzt.

## 2.10.1

- Diagnose der Zeitleiste im Popup „Wertentwicklung“ (aufklappbar, ohne Beträge): Seiten, Einträge, Einträge mit ISIN, eigene Positionen, Stückzahlen, Fehler.
- Käufe/Verkäufe ohne Stückzahl in den Details (Order, Sparplan, Saveback, Round-up) werden behalten; die Stückzahl wird aus Betrag und Tageskurs geschätzt.
- Stückzahl wird in mehr Antwortformen erkannt.

## 2.10.0

- Wertentwicklung im Popup (kleiner Button „📈 Wertentwicklung“ in der Statistik).
- Grafik in Säulenfarben gestapelt: Welt grün, Gold gelb, Cash blau (Cash vor Käufen zurückgerechnet).
- Prüfung der Kaufhistorie: zeigt, ob alle heutigen Stücke durch erkannte Käufe erklärt sind; sonst sind die Gewinne als Annahme (≈) markiert.
- Prozentwerte in Statistik und Angleichen-Tabelle mit zwei Nachkommastellen.
- Fehler behoben: Die Liste der Käufe/Verkäufe brach die Anzeige im Papierdepot ab.

- Historie korrigiert: Dividenden, Ausschüttungen, Zinsen und Steuerbuchungen aus der Zeitleiste zählen nicht mehr als Verkäufe (sie verfälschten die Stückzahlen in der Vergangenheit). Nur Einträge mit Stückzahl gelten als Kauf/Verkauf; die Richtung kommt aus der Art der Buchung.
- Transaktionen werden bei jedem Abgleich komplett neu gelesen; frühere Fehldeutungen verschwinden.
- Je Position aufklappbar: die erkannten Käufe/Verkäufe (Datum, Art, Stück, Betrag) zum Nachprüfen; im Log je Transaktion eine Zeile.

## 2.9.0

- Statistik: Zeiträume 1 Woche, 1/3/6 Monate, seit 1.1., 1/3/5 Jahre und Max., jeweils mit Gewinn je Säule.
- Echte Historie: Beim Synchronisieren liest die App die Käufe und Verkäufe aus der Trade-Republic-Zeitleiste. Der Verlauf rechnet je Tag mit den damals gehaltenen Stückzahlen; der Gewinn eines Zeitraums zählt neu investiertes Geld nicht mit. „Gehalten seit“ kommt aus dem ersten Kauf der laufenden Position. Käufe/Verkäufe als ▲/▼ in der Grafik und im Tooltip. Cash ist im Verlauf nicht enthalten.
- Interaktive Grafik: Maus oder Finger zeigt für jeden Tag Gesamtwert, Veränderung seit Beginn des Zeitraums und die Werte je Säule; Achsen mit Werten und Datum.

## 2.8.0

- CallMeBot entfernt. Meldungen gehen nur noch über einen Dienst in Home Assistant, Standard: whatsapp.send_message von „WhatsApp for Home Assistant“ (FaserF).
- Empfänger wird normalisiert (0171… → +49171…, Gruppen-IDs …@g.us bleiben), höchstens eine Nachricht pro Sekunde, 10 s Timeout.
- Die alte WhatsApp-Nummer dient als Empfänger, solange „Empfänger“ leer ist.

## 2.7.0

- Statistik: Entwicklung der heutigen Bestände über 1 Monat, 6 Monate und 1 Jahr (Gewinn in € und %) mit umschaltbarer Grafik aus Tagesschlusskursen. Junge Produkte ohne lange Kurshistorie werden mit dem gleichwertigen Säulen-Instrument fortgeschrieben.

## 2.6.0

- Benachrichtigungen auch über einen Dienst in Home Assistant (Optionen „Benachrichtigungsdienst“ und „Empfänger“), z. B. whatsapp.send_message von „WhatsApp for Home Assistant“, die Home-Assistant-App oder Telegram – zusätzlich zu oder statt CallMeBot.
- Statistik zeigt den Gewinn von heute: gesamt (in € und %) und je Säule, aus der Tagesänderung der Positionen; physisches Gold mit der Änderung des Goldpreises.

- Haltedauer: Spalte „Gehalten“ in der Statistik (älteste Position der Säule, z. B. „3 Wochen“, „1 Jahr 3 M.“) und „Gehalten seit“ je Position. Trade Republic liefert kein Kaufdatum – gezählt wird ab dem ersten Abgleich, das Datum lässt sich je Position über „ändern“ korrigieren. Physisches Gold nutzt das eingetragene Kaufdatum.

## 2.5.2

- QR-Code wird quadratisch und vollständig angezeigt (SVG mit viewBox, feste Größe, breiterer Rand) – vorher konnte er beschnitten oder verzerrt sein und ließ sich nicht scannen.

## 2.5.1

- Zinszeile ohne den Zusatz zum EZB-Einlagensatz.

## 2.5.0

- Rechte Spalte zeigt im echten Depot die gekauften Produkte statt des Referenz-Instruments (z. B. Invesco Physical Gold statt Xetra-Gold), bei mehreren Produkten einer Säule (zwei IMI-ETFs) alle mit Kurs und Tagesänderung. Das Signal kommt weiter vom Referenz-Instrument.

## 2.4.1

- Rechte Spalte (Säulen-Details) schmaler: Übersicht 60 %, Details 40 %.

## 2.4.0

- Säulen in Cash sind klar gekennzeichnet („in Cash“); die Angleichen-Tabelle sagt „als Cash halten“ / „aus Cash nehmen“ statt kaufen/verkaufen.
- Neue Option **Cash-Reserve außerhalb der Strategie**: dieser Teil des TR-Guthabens zählt nicht zu den Säulen.
- Zinssatz: ohne Angabe von Trade Republic gilt der EZB-Einlagensatz (täglich von der EZB).

## 2.3.1

- US-Erstanträge: Ein Monat gilt erst als vollständig, wenn die Woche bis zu seinem letzten Samstag gemeldet ist. Bisher wurde Anfang des Monats – genau zur Monatsentscheidung – oft der Vormonat ohne seine letzte Woche ausgewertet.

## 2.3.0

- Trade Republic bleibt nie verbunden: Nach dem Login liest die App einmal Positionen, Cash und Zinssatz, speichert den Stand und meldet sich sofort wieder ab. Die Kurse laufen weiter. Button **Neu synchronisieren** für einen neuen Abgleich (erneut anmelden).
- Aufgeräumte Säulenansicht: ein Balken je Säule in der Säulenfarbe, Produkte als Abschnitte, Cash schraffiert; kein Lila mehr.
- Nicht zugeordnete Positionen stehen jetzt oben in den letzten Meldungen.

## 2.2.2

- Letzte Meldungen in einem kleinen Fenster zum Scrollen.
- „Angleichung übernehmen“ nur noch im Papierdepot; im echten Depot wird bei Trade Republic angeglichen.

## 2.2.1

- Echtes Depot: Beträge und Kaufbudgets immer als 40/30/30 vom tatsächlichen Depotwert; der eingestellte Gesamtbetrag gilt nur noch für das Papierdepot.
- Angleichen-Tabelle passt auf schmale Karten.
- Kleine Abweichungen bis ±5 Prozentpunkte lösen keine rote Meldung mehr aus; sie zeigen nur die Balken (mit Hinweis „im Rahmen“).
- Positionen werden mit dem Wert bewertet, den Trade Republic selbst liefert (statt eigenem Geldkurs).
- Abgleich unter der Statistik: Wert laut Trade Republic, was davon in den Säulen zählt, Cash und nicht zugeordnete Positionen.

## 2.2.0

- Zinsen auf Cash: Der Zinssatz von Trade Republic wird bei jedem Abgleich gelesen (oder als eigener Wert in den Optionen gesetzt). Die Statistik zeigt Satz, Cash und Zinsen im Jahr, neuer Sensor `sensor.saeulenwaechter_zins`.
- Papierdepot: Säulen in Cash bekommen die Zinsen täglich gutgeschrieben.
- Depot wird wie in der TR-Web-App über `compactPortfolioByTypeV2` gelesen; Kaufkurse als Betrag-Objekt werden erkannt. Die Kaufkurse stehen im Log zum Abgleich.
- Echtes Depot: Säulen ohne Position zählen mit ihrem Anteil am Cash bei Trade Republic statt mit dem konfigurierten Betrag. Gesamtwert und Angleichen waren dadurch zu hoch bzw. falsch.
- Angleichen wird als Tabelle angezeigt: Ist, Ziel, Anteil und was zu kaufen oder zu verkaufen ist.

## 2.1.0

- **Login per QR-Code:** in der Oberfläche den QR-Code mit der Handy-Kamera oder der Trade-Republic-App scannen und
  in der App bestätigen – ohne PIN und ohne Authenticator-Code. Der Code erneuert sich automatisch.
- **Physisches Gold:** Barren und Münzen mit Menge (g oder oz), Feingehalt und Kaufpreis eintragen. Das Gold zählt
  zur Gold-Säule (Wert, Statistik, Verlauf, Bestandsbalken), wird mit dem Goldpreis je Gramm (Xetra-Gold)
  bewertet; Kaufanweisungen ziehen es ab, bei einem Verkaufssignal bleibt es liegen. Neue Entität
  `sensor.saeulenwaechter_physisches_gold`.
- Die App meldet Trade Republic jetzt die aktuelle Version der Web-App (automatisch ermittelt) und die richtige
  Zeitzone (Sommerzeit).

## 2.0.2

- Trade-Republic-Login mit Authenticator-Code: ein abgelehnter Code (`AUTHENTICATION_ERROR`) zeigt jetzt
  „Code nicht angenommen“, der Login bleibt offen und ein neuer Code lässt sich ohne PIN eingeben.
- Code wird bereinigt (Leerzeichen), nach dem Code wartet die App auf die Session wie die TR-Web-App.
- Verlangt Trade Republic während der App-Bestätigung doch einen Code, wechselt die Seite dorthin.
- Abgelehnte Login-Schritte stehen mit Status und Fehlercode von Trade Republic im App-Protokoll.

## 2.0.1

- Installation schlug fehl („pip: not found“): Der Supervisor hat `build.yaml` verworfen und mit seinem
  Standard-Image ohne Python gebaut. Das Basisimage steht jetzt fest im Dockerfile, `build.yaml` entfällt.

## 2.0.0

- Der Säulenwächter ist jetzt eine **Home-Assistant-App** statt einer HACS-Integration. Updates kommen über den
  App-Store von Home Assistant.
- Oberfläche in der Seitenleiste (Ingress) mit Trade-Republic-Login, Statistik, Verlauf, Säulen und Signalen.
- Entitäten `sensor.saeulenwaechter_*` / `binary_sensor.saeulenwaechter_*` mit denselben IDs wie bisher, neu:
  `sensor.saeulenwaechter_gewinn_verlust` und `binary_sensor.saeulenwaechter_handlung_noetig`.
- Umstieg: die alte Integration löschen und in HACS entfernen, danach in der App einmal bei Trade Republic
  anmelden.

## 1.1.0

- Depot per ISIN erkennen (gleichwertige Produkte, eigene ISINs), nicht zugeordnete Positionen.
- Säulenstatistik mit Verlauf, roter Hinweis bei nötiger Handlung, TR-Verteilung je Säule.
