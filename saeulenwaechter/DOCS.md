# Säulenwächter

## Einrichten

1. **Konfiguration:** Gesamtbetrag (Summe der drei Säulen, im Papiermodus das Startkapital), WhatsApp-Nummer
   im internationalen Format ohne `+` (z. B. `4917…`) und CallMeBot-API-Key eintragen und speichern.
2. **Starten** und „In Seitenleiste anzeigen“ einschalten.
3. In der Oberfläche unten **Bei Trade Republic anmelden**: den QR-Code mit der Handy-Kamera oder der
   Trade-Republic-App scannen und in der App bestätigen. Alternativ Telefonnummer und 4-stellige PIN, danach
   in der App bestätigen oder den Code aus der Authenticator-App eingeben. Gespeichert wird nur die Web-Session,
   nie die PIN. Ohne Login rechnet die App mit einem Papierdepot.

## Physisches Gold

Gold, das du außerhalb von Trade Republic besitzt (Barren, Münzen), trägst du in der Oberfläche unter
**Physisches Gold** ein: Bezeichnung, Menge in Gramm oder Unzen, Feingehalt (999,9 für Barren, 916,7 für
Krügerrand) und Kaufpreis. Es zählt zur Gold-Säule und wird mit dem Goldpreis je Gramm (Geldkurs von Xetra-Gold,
ein Anteil = ein Gramm) bewertet. Kaufanweisungen für die Gold-Säule ziehen seinen Wert ab; deckt es die Säule
ab, heißt es „halten“. Bei einem Verkaufssignal betrifft die Anweisung nur den ETC, das physische Gold bleibt.

## Optionen

| Option | Bedeutung |
|---|---|
| Gesamtbetrag | Summe der drei Säulen (40/30/30). Eine Änderung setzt die Beträge neu. |
| WhatsApp-Nummer, CallMeBot API-Key | Ziel der Meldungen. |
| WhatsApp-Meldungen senden | Aus: nur Anzeige in der Oberfläche. |
| Monatsbericht auch ohne Änderung | Jeden Monat eine Zusammenfassung. |
| Vorwarnung | Meldung, wenn ein Signal zum Monatsende kippen würde (letzte 7 Tage). |
| Monat für das jährliche Angleichen | 1–12. |
| Echtes Trade-Republic-Depot verwenden | Aus: Papierdepot, auch mit Login. |
| Weitere ISINs Welt / Gold / Anleihen | Eigene Produkte, die wie das Säulen-Instrument zählen (kommagetrennt). |
| BLS-API-Key | Optional, für mehr Abrufe der US-Arbeitslosenquote. |

Nach dem Speichern startet die App neu.

## Entitäten

Die App schreibt `sensor.saeulenwaechter_*` und `binary_sensor.saeulenwaechter_*` über die Home-Assistant-API,
z. B. `sensor.saeulenwaechter_welt_zustand`, `sensor.saeulenwaechter_gold_aktion`,
`sensor.saeulenwaechter_depotwert`, `sensor.saeulenwaechter_gewinn_verlust` und
`binary_sensor.saeulenwaechter_handlung_noetig` und `sensor.saeulenwaechter_physisches_gold`. Sie werden jede
Minute erneuert.

## Daten und Sicherheit

- Der Zustand (Entscheidungen, Papierdepot, Verlauf, TR-Session) liegt in `/data/state.json` der App und ist
  Teil der Home-Assistant-Sicherung.
- Die Oberfläche ist nur über Home Assistant (Ingress) erreichbar.
- Die Trade-Republic-API ist inoffiziell und kann sich ändern. Der Säulenwächter liest nur und handelt nie selbst.
- Keine Anlageberatung.
