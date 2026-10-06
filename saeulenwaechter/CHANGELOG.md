# Changelog

## 2.6.0

- Statistik zeigt den Gewinn von heute: gesamt (in € und %) und je Säule, aus der Tagesänderung der Positionen; physisches Gold mit der Änderung des Goldpreises.

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
