# Entwürfe

Hier liegen die gelieferten Design-Vorlagen, ein Ordner je Bildschirm. Sie sind **Referenz, kein
Produktionscode**: die HTML-Dateien zeigen Aussehen und Verhalten, nachgebaut wird in React mit
Tailwind und shadcn/ui unter `app/`.

| Ordner | Bildschirm | Stand |
| --- | --- | --- |
| `startbildschirm/` | Start, mobil (390 px) und Desktop (1440 px), dunkles Design | umgesetzt |

Je Ordner:

- `handoff.md` – die verbindliche Beschreibung: Maße, Farben, Zustände, Verhalten
- `entwurf.html` – der Prototyp, im Browser direkt zu öffnen
- `support.js` – Laufzeit der Vorschau, gehört **nicht** zur Umsetzung
- `assets/` – freigestellte Logodateien

Die Design-Tokens aus den Handoffs stehen gesammelt in `app/src/index.css` und gelten für alle
Bildschirme, auch für die noch nicht entworfenen. Das helle „Pergament"-Design ist vorbereitet,
aber noch nicht gestaltet.

## Bewusste Abweichungen

Die Handoffs bleiben unverändert, so wie geliefert. Wo die Umsetzung davon abweicht, steht es hier.

| Abweichung | Grund |
| --- | --- |
| **Keine zweite Schrift.** Der Handoff sieht Cinzel für App-Namen und große Titel vor, umgesetzt ist durchgehend Inter. | Entscheidung vom 2026-09-20: die Mischung aus Serifen- und serifenloser Schrift wirkt uneinheitlich. Dazu kommt, dass die gelieferte Wortbildmarke `muninn-logo.png` „MUNINN" in einer Grotesk zeigt — die Cinzel-Wortmarke in der Kopfleiste passte also ohnehin nicht zum Logo daneben. |
