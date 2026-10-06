# Changelog

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
