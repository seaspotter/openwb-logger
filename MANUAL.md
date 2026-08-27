# openWB Logger – Bedienungsanleitung

Kurze Referenz für die Weboberfläche. Für Installation/Konfiguration siehe
[DEPLOYMENT.md](DEPLOYMENT.md), für die Architektur [CLAUDE.md](CLAUDE.md).

## Kopfzeile

- **Alle Quellen** — welches der aktivierten Logs angezeigt wird (welche
  Logs überhaupt *erfasst* werden, wird in den Einstellungen festgelegt,
  siehe unten).
- **Tag-Auswahl** — `Heute (live)` zeigt die neuesten Zeilen und aktualisiert
  automatisch (siehe **Live** unten); jeder andere Eintrag ist ein
  bestimmter, abgeschlossener Kalendertag.
- **Zeitraum** — überschreibt die Tag-Auswahl: ein beliebiges von/bis
  wählen (löst die Tag-Auswahl und **Live** ab, solange gesetzt), oder
  einen der Schnellauswahl-Knöpfe (**15 Min / 30 Min / 1 Std / 2 Std**)
  anklicken, der von/bis automatisch auf "jetzt minus N" setzt und sofort
  lädt. Das **×** daneben setzt den Zeitraum zurück. In diesem Modus wird
  das gesamte Ergebnis in einer Anfrage geladen (kein Blättern), aber nach
  100000 Zeilen begrenzt — bei einer Meldung dazu den Zeitraum enger
  fassen.
- **Alle Level** — nach Log-Level filtern (DEBUG/INFO/WARNING/ERROR/...).
- **Suchen** — Volltextfilter über die Rohzeile; nur Treffer werden
  angezeigt, nicht nur hervorgehoben.
- **Live** — solange aktiv, wird "Heute (live)" alle 5 Sekunden neu
  geladen und ans Ende gescrollt. Schaltet sich automatisch ab, sobald man
  wegscrollt, das Level ändert, sucht, oder einen Zeitraum wählt — dann
  muss man es bei Bedarf wieder anklicken.

## Blättern

**← älter** / **neuer →** blättern seitenweise durch den aktuell gewählten
Tag (nicht im Zeitraum-Modus, dort ist alles auf einmal geladen). Die
Knöpfe deaktivieren sich automatisch, wenn es in die jeweilige Richtung
nichts mehr gibt.

## Rechte Seite

- **Exportieren** — lädt genau den aktuell aktiven Filter (Quelle,
  Tag-oder-Zeitraum, Level, Suche) als Textdatei herunter (oder als
  komprimierte `.gz`-Datei, siehe "Exportierte Datei komprimieren" unten).
  Deaktiviert während **Live** aktiv ist — vorher einen Tag/Zeitraum
  wählen oder **Live** abschalten.
- **An Paste senden** — wie Exportieren, aber lädt stattdessen zu openWBs
  eigenem Paste-Dienst hoch und zeigt einen Link zum Teilen (landet auch
  in der Zwischenablage, falls der Browser das zulässt).
- **⇅** — kehrt die Anzeigereihenfolge um (älteste/neueste zuerst); merkt
  sich die Wahl im Browser.
- **Jetzt abrufen** — löst sofort einen Abruf aus, ohne auf das nächste
  planmäßige Intervall zu warten.
- **☀/🌙** — Hell/Dunkel umschalten; merkt sich die Wahl im Browser
  (Systemeinstellung entscheidet nur beim allerersten Besuch).
- **⚙** — öffnet die Einstellungen (siehe unten).

## Statuszeile

- **Quelle** — die konfigurierte openWB-Adresse, von der abgerufen wird.
- **Abruf** — das aktuelle Abrufintervall.
- **Aufbewahrung** — wie lange Zeilen aufbewahrt werden, bevor sie
  automatisch gelöscht werden.
- **Zeilen** — Gesamtzahl gespeicherter Zeilen (ungefähr, nicht exakt
  gezählt — das wäre bei Millionen Zeilen unnötig teuer).
- **Letzter Abruf** — Zeitpunkt des letzten Abrufversuchs.
- **Nicht erreichbar** — listet Quellen, die beim letzten Abruf nicht
  erreichbar waren (Mauszeiger für die genaue Fehlermeldung je Quelle);
  meist ein Zeichen, dass die openWB-Adresse in den Einstellungen nicht
  (mehr) stimmt, oder dass der Container das falsche Netzwerk sieht.
- **Fehler** — erscheint nur bei einem unerwarteten Fehler im gesamten
  Abruflauf (z. B. ein Datenbankproblem), nicht bei einer einzelnen
  nicht erreichbaren Quelle — dafür siehe "Nicht erreichbar" oben.
- **Lücken** — Anzahl erkannter Lücken zwischen zwei Abrufen (weil
  openWBs Log zwischendurch rotiert ist) und wie viele davon aus den
  rotierten Sicherungsdateien wiederhergestellt werden konnten. Wenn
  "wiederhergestellt" hinter "erkannt" zurückbleibt, gingen tatsächlich
  Zeilen verloren — Abhilfe: kürzeres Abrufintervall in den Einstellungen.
- **Format-Warnung** — erscheint, wenn ein ungewöhnlich großer Teil der
  zuletzt abgerufenen Zeilen einer Quelle nicht zum erwarteten Format
  passte (z. B. wenn openWB sein Log-Format ändert). Ein einzelner
  mehrzeiliger Traceback reicht dafür nicht aus.

## Einstellungen (⚙)

- **openWB-Adresse / Ramdisk-Pfad** — wo openWB erreichbar ist.
- **Zu erfassende Logs** — welche der bekannten openWB-Logs überhaupt
  abgerufen werden (unabhängig von der Quellenauswahl oben in der
  Kopfzeile, die nur die *Anzeige* filtert). Eine neu aktivierte Quelle
  wird beim ersten Abruf rückwirkend aus openWBs vorhandenen
  Sicherungsdateien befüllt, nicht nur ab jetzt.
- **Abrufintervall** — wie oft abgerufen wird. Faustregel: kürzer als die
  Zeit, die die jeweils schnellste aktivierte Quelle zum Rotieren
  braucht, sonst drohen Lücken (siehe oben).
- **Aufbewahrung** — nach wie vielen Tagen Zeilen automatisch gelöscht
  werden.
- **Zeilen pro Seite** — wie viele Zeilen auf einmal geladen werden (gilt
  für "Heute (live)" und normales Blättern; Zeitraum hat eine eigene,
  höhere Grenze, siehe oben).
- **Exportierte Datei komprimieren (.gz)** — lädt "Exportieren" als
  komprimierte `.gz`-Datei statt als Textdatei herunter (nützlich bei
  großen Exporten). Eine reine Browser-Einstellung (im Browser
  gespeichert), betrifft nicht "An Paste senden" — der Upload dorthin wird
  ohnehin immer komprimiert übertragen, unabhängig von dieser Einstellung.
- **Paste-Upload-URL / Paste-Anzeige-URL** — wohin "An Paste senden"
  hochlädt bzw. wie der angezeigte Link aufgebaut wird. Nur ändern, falls
  ein anderer Paste-Dienst genutzt werden soll.
- **Retention-Job** — zeigt, ob TimescaleDBs eigener Aufbewahrungs-Job
  gerade funktioniert. Bei "Fehlgeschlagen" erscheint ein
  **Reparieren**-Knopf (mit Bestätigungsdialog): behebt einen bekannten
  TimescaleDB-Fehler, bei dem der Job dauerhaft mit "no chunk found with
  ID N" fehlschlägt und alte Daten dadurch nie automatisch gelöscht
  werden (siehe [DEPLOYMENT.md](DEPLOYMENT.md)). Entfernt nur Metadaten
  bereits gelöschter Chunks, keine echten Log-Daten.
- **Version / Update** — zeigt den aktuellen Commit; **Prüfen** vergleicht
  gegen das konfigurierte Git-Remote, ohne etwas zu verändern; **Update**
  lädt die neueste Version und startet die Anwendung neu. Beide Knöpfe
  sind deaktiviert, wenn Self-Update in dieser Installation nicht
  eingerichtet ist (siehe [DEPLOYMENT.md](DEPLOYMENT.md)).

Alle Einstellungen wirken sofort, ohne Neustart des Containers.
