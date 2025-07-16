1.  **Änderungen hinzufügen (`git add`)**
2.  **Änderungen speichern (`git commit`)**
3.  **Änderungen hochladen (`git push`)**

-----

### Dein neuer Arbeitsablauf

Wenn du in Zukunft Änderungen an deiner `index.html` oder anderen Dateien vorgenommen hast, gib einfach die folgenden Befehle in dein Terminal ein:

**1. Alle geänderten Dateien zum "Einpacken" vormerken:**

Der Punkt steht wieder für "alle Dateien". Da deine `.gitignore` jetzt korrekt ist, werden `node_modules` und andere ignorierte Dateien übersprungen.

```bash
git add .
```

**2. Den Änderungen einen Namen (eine "Commit-Nachricht") geben:**

Ersetze `"Neue Funktion hinzugefügt"` mit einer kurzen Beschreibung dessen, was du geändert hast. Das hilft dir später, deine Änderungen nachzuvollziehen.

```bash
git commit -m "Drag & Drop für Warteschlange implementiert"
```

**3. Die Änderungen auf GitHub hochladen:**

Da du beim ersten Mal die Verbindung mit `-u origin main` hergestellt hast, merkt sich Git das. Ab jetzt reicht der einfache Befehl:

```bash
git push
```

-----

**Das war's schon\!** Nachdem du `git push` ausgeführt hast, erkennt **Render** automatisch die Änderung in deinem GitHub-Repository und wird deine Webseite innerhalb von ein oder zwei Minuten automatisch mit dem neuen Code aktualisieren.

**Tipp:** Du kannst jederzeit mit `git status` überprüfen, welche Dateien du geändert hast, bevor du die Befehle ausführst.
