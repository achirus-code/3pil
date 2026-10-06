# Changelog

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
