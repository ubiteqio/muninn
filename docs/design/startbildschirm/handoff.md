# Handoff: Muninn – Startbildschirm (Mobil + Desktop, dunkles Design)

## Overview
Muninn macht ca. 26 Jahre Familienfotos und -videos von einem NAS als Bibliothek durchsuchbar:
Alben aus der Ordnerstruktur, Zeitleiste, KI-Suche in natürlicher Sprache, Gesichter, Karte der
Aufnahmeorte, Rückblicke „Heute vor X Jahren", Likes/Kommentare/Favoriten für angemeldete
Familienmitglieder. Name und Bildsprache stammen aus der nordischen Mythologie (Muninn = Odins
Rabe der Erinnerung).

Dieses Paket enthält den **Startbildschirm** in zwei Breakpoints (Mobil 390 px, Desktop 1440 px)
im **dunklen Design**. Die übrigen Kernbildschirme (Album, Medium-Vollbild, Suche, Karte), die
Zusatzbildschirme (Anmeldung, Profil, Personen, Admin) und das helle „Pergament"-Design sind noch
nicht entworfen — die hier dokumentierten Tokens und Muster gelten aber bereits für sie.

## About the Design Files
Die Dateien in diesem Bundle sind **Design-Referenzen in HTML** — Prototypen, die Aussehen und
Verhalten zeigen, **kein Produktionscode zum Kopieren**. Aufgabe ist es, diese Entwürfe in der
Zielumgebung nachzubauen: geplant sind **React + Tailwind CSS + shadcn/ui**. Komponenten,
Abstände und Varianten sollen aus dem bestehenden shadcn/ui-Setup kommen (Card, Button, Badge,
Avatar, ScrollArea, Sheet, Tabs, Input …); die HTML-Datei dient als visuelle Spezifikation.
Existiert noch kein Setup, ist React + Tailwind + shadcn/ui die empfohlene Grundlage.

Die App ist eine responsive Web-App, die zusätzlich als iOS- und Android-App laufen soll — jeder
Bildschirm braucht also eine Mobil- und eine Desktopvariante.

## Fidelity
**High-fidelity.** Farben, Typografie, Abstände, Radien und Zustände sind final gemeint und sollen
pixelgenau übernommen werden. Ausnahme: alle Fotos sind farbige Verlaufs-Platzhalter
(entsprechen bewusst den Lade-Platzhaltern, s. u.) — dort kommen echte Medien aus dem NAS-Index.

## Screens / Views

### 1. Start – Mobil (390 × 844)

**Zweck:** Einstieg. Erinnerungen anstoßen (Rückblicke), sehen was die Familie gemacht hat
(Neuigkeiten), neue Alben finden, in der Gesamt-Zeitleiste stöbern.

**Layout (von oben):**
| Bereich | Höhe / Position | Details |
|---|---|---|
| Statusleiste | 52 px, fix | Uhrzeit links, Systemicons rechts, Verlauf `#0B0D12 → transparent` |
| Kopfleiste | 60 px, sticky (`top:52px`) | `background: rgba(11,13,18,0.86)`, `backdrop-filter: blur(14px)`, untere Linie `rgba(200,205,214,0.08)`, Padding `0 20px` |
| Scrollbereich | `inset: 112px 0 0 0`, `padding-bottom: 110px` | enthält die vier Sektionen |
| Navigationsleiste | 58 px + 22 px Safe Area, fix unten | `rgba(18,26,43,0.96)`, `blur(18px)`, Oberkante `rgba(200,205,214,0.09)` |

**Kopfleiste:** links Logo-Kachel 38 × 38 px, Radius 11 px, Hintergrund `#EDE6D6` (Pergament —
das Logo ist dunkelblau und braucht auf Rabenschwarz eine helle Fläche), Rand
`1px rgba(237,230,214,0.5)`, darin `muninn-mark.png` 31 × 31 px `object-fit: contain`; daneben
Wortmarke „MUNINN", **Cinzel 600, 20 px, letter-spacing 0.15em**, `#EDE6D6`.
Rechts: Glocken-Button 44 × 44 px (`#C8CDD6`, Hover `background:#1C2740`, `color:#EDE6D6`,
Radius 12 px) mit Bernstein-Punkt 8 px (`#E3A73B`, 2 px Rand in `#0B0D12`); Avatar 34 px rund,
Initialen 13/700 in `#0B0D12`.

**Sektion „RÜCKBLICKE":** Überschrift Inter 600, 11 px, `letter-spacing: 0.16em`, uppercase,
`#C8CDD6`; rechts „Alle ansehen" 12 px/500 in `#E3A73B`.
Horizontaler Scroller (`scroll-snap-type: x mandatory`, Gap 12 px, Padding `0 20px`) mit Karten
250 × 316 px, Radius 12 px:
- Foto füllt die Karte; darüber Verlauf
  `linear-gradient(180deg, rgba(11,13,18,.55) 0%, rgba(11,13,18,0) 34%, rgba(11,13,18,.1) 52%, rgba(11,13,18,.86) 100%)`
- Chip oben links: `rgba(11,13,18,0.62)` + `blur(8px)`, Rand `1px rgba(227,167,59,0.4)`, Radius 999,
  Icon `history` 15 px `#E3A73B`, Text 11/600 `#F4C878` — z. B. „Heute vor 5 Jahren"
- unten: Titel **Cinzel 600, 22 px** `#EDE6D6`, darunter Meta 12 px `#C8CDD6`
  („19. September 2021 · 24 Fotos")

**Knotwork-Trenner:** Höhe 8 px, `opacity: .1`, zwei gekreuzte
`repeating-linear-gradient(±45deg, #C8CDD6 0 1px, transparent 1px 8px)`, `background-size: 8px 8px`.
Nur zwischen Sektionen, **nie über Fotos**.

**Sektion „NEUIGKEITEN":** Card `#121A2B`, Rand `1px rgba(200,205,214,0.07)`, Radius 12 px.
Zeilen ≥ 64 px, Padding 12 px, Trennlinie `rgba(200,205,214,0.06)`:
Avatar 38 px rund + Status-Badge 19 px (`#1C2740`, 2 px Rand `#121A2B`) mit Icon 11 px
(`chat_bubble`, `add_photo_alternate`, `favorite` — Favorit in `#E3A73B`, sonst `#C8CDD6`);
Text 13,5 px `#EDE6D6` mit fettem Namen (600); Zeile 2: 11,5 px `#C8CDD6` („Italien 2009 · vor 2 Std.");
rechts Thumbnail 42 × 42 px, Radius 8 px.
Beispielinhalte: „**Anna** hat ein Foto kommentiert", „**Papa** hat 8 Medien hinzugefügt",
„**Lena** gefällt dein Foto".

**Sektion „ZULETZT HINZUGEFÜGT":** rechts Label „Yggdrasil" (12 px/500, `#E3A73B`).
Horizontaler Scroller, Karten 132 px breit: Cover 132 × 132 px, Radius 12 px, Zählchip unten rechts
(`rgba(11,13,18,0.66)`, Radius 6, 10,5/600 `#EDE6D6`); Titel 13/600 `#EDE6D6`; Pfad 11,5 px
`#C8CDD6` („Reisen › 2009").

**Sektion „ZEITLEISTE":** Kopfzeile mit Bernstein-Chip rechts, der das aktuell sichtbare Datum
zeigt: `background: rgba(227,167,59,0.16)`, Text `#F4C878`, 11/700, Radius 999.
Datumsgruppen („Heute · 19. September 2026", „Gestern", „September 2026") als Label 12,5/600
`#EDE6D6`, darunter Raster **3 Spalten, Gap 2 px**, Kacheln quadratisch.
Rechts am Rand der Datums-Schieberegler: Spur 40 px breit mit Jahresmarken 2026/2020/2014/2007/2000
(9,5/600 `#C8CDD6`, Strich 6–10 px `rgba(200,205,214,0.35)`) und Bernstein-Griff 6 × 30 px,
Radius 3, `#F4C878`, Glow `0 0 14px rgba(244,200,120,0.35)`.
Das Raster reserviert `padding-right: 40px`, damit Griff und Jahre **nie** auf Fotos liegen.
Kachel-Overlays: Video-Badge oben rechts (`play_arrow` + Dauer, `rgba(11,13,18,0.6)`, Radius 5);
geschätztes Datum unten links dezent als „≈ 2005" (10 px `#C8CDD6`, `rgba(11,13,18,0.55)`).

**Navigationsleiste:** 5 gleich breite Ziele à 58 px Höhe (Touch-Ziel ≥ 44 px erfüllt):
Start (`home`), Alben (`photo_library`), Suche (`search`), Karte (`map`), Profil (`person`).
Aktiv: Icon gefüllt (`FILL 1`) + Label 600 in `#E3A73B`; inaktiv `#C8CDD6`, `FILL 0`, 500.
Icon 24 px, Label 10,5 px. Home-Indicator 134 × 5 px, `rgba(237,230,214,0.28)`.

### 2. Start – Desktop (1440 × 960)

**Seitenleiste links, 96 px breit**, `#121A2B`, rechte Kante `rgba(200,205,214,0.08)`:
Logo-Kachel 48 px (Radius 13, `#EDE6D6`) → Wortmarke „MUNINN" Cinzel 10,5 px, `letter-spacing:0.18em`,
`#C8CDD6` → Knotwork-Strich 40 × 8 px → Navigationsziele als Blöcke 64 px hoch, Radius 12,
Icon 24 px + Label 10,5 px, aktiv `background: rgba(227,167,59,0.12)` + `#E3A73B`;
unten Profil-Avatar 40 px.

**Kopfzeile, 76 px**, Padding `0 32px`, untere Linie `rgba(200,205,214,0.08)`:
Titel „Start" Cinzel 600, 22 px; Suchfeld (max. 520 px, 44 px hoch, `#121A2B`, Rand
`rgba(200,205,214,0.1)`, Radius 12) mit `search`-Icon und Hinweistext
„Mímir fragen – z. B. „Oma am Strand 2012""; rechts Primärbutton **„Hochladen"**
(44 px hoch, Radius 12, `#E3A73B`, Text `#0B0D12` 14/600, Hover `#F4C878`, Icon `upload`) und
Glocken-Button 44 px mit Rand `rgba(200,205,214,0.12)`.

**Inhalt: Grid `minmax(0,1fr) 352px`**, beide Spalten eigenständig scrollbar.
- **Links** (Padding `26px 28px 40px`): Rückblicke als 3-Spalten-Grid, Karten 280 px hoch, Gap 16 px
  (gleiche Gestaltung wie mobil, Titel 23 px) → Knotwork-Trenner → Zeitleiste mit Kopfzeile
  („84 312 Medien · 1999 – 2026" + Bernstein-Datumschip), Raster **8 Spalten**, Gap 2 px,
  `padding-right: 56px` für die Jahresspur (44 px) und den Griff (6 × 32 px).
- **Rechts** (352 px, `#0E1219`, linke Kante `rgba(200,205,214,0.08)`): Neuigkeiten-Card (identisch
  zu mobil, Thumbnail 44 px) und „Zuletzt hinzugefügt" als 2-Spalten-Grid, Cover `aspect-ratio: 1`,
  Gap 14 px.

## Interactions & Behavior
- **Rückblick-Karte** → öffnet das Album des Tages („Heute vor X Jahren"), Klickfläche = ganze Karte.
- **Neuigkeiten-Zeile** → springt zum betroffenen Medium bzw. Kommentar.
- **Albumkarte** → Albumbildschirm; „Yggdrasil" / „Alle ansehen" → jeweilige Übersicht.
- **Zeitleisten-Kachel** → Medium im Vollbild (Wischen zum nächsten Bild).
- **Datums-Schieberegler**: Ziehen scrollt die Zeitleiste; der Bernstein-Chip in der Sektions-
  überschrift zeigt live den Monat der obersten sichtbaren Zeile. Der Griff darf niemals über
  Fotokacheln liegen — Raster immer mit Reserve rechts rendern.
- **Hover (Desktop)**: Karten +2 % Helligkeit oder Rand `rgba(227,167,59,0.35)`; Buttons wie oben.
- **Fokus**: 2 px Outline in Goldlicht `#F4C878`, Offset 2 px — sichtbar auf allen Bedienelementen.
- **Laden**: farbige Unschärfe-Platzhalter (dominante Farbe des Mediums, `filter: blur(12px)`),
  **keine grauen Kästen**; App-weite Ladeanimation: zwei Raben, die einander umkreisen.
- **Leere Zustände**: kurzer Satz + Knotwork-Ornament bei 10 % Deckkraft, z. B. „Walhall ist noch leer".
- **Geschätzte Daten** werden dezent mit „≈ Jahr" markiert.
- **Responsive**: < 768 px Mobil-Layout mit unterer Navigationsleiste; ≥ 1024 px Seitenleiste +
  zweispaltiger Inhalt; dazwischen Seitenleiste + einspaltig, Neuigkeiten unter die Zeitleiste.

## State Management
- `memories[]` – Rückblicke des Tages (Datum, Album, Medienzahl, Cover).
- `activity[]` – Neuigkeiten-Feed (Akteur, Typ: comment | upload | like, Ziel, Zeitstempel).
- `recentAlbums[]` – zuletzt indizierte Alben (Titel, Pfad, Anzahl, Cover).
- `timeline` – paginiertes/virtualisiertes Medien-Raster, gruppiert nach Tag/Monat.
- `scrubberDate` – abgeleitet aus der Scrollposition (throttled), speist den Datumschip.
- `unreadCount` – steuert den Bernstein-Punkt an der Glocke.
- Datenbedarf: Rückblicke pro Tagesdatum, Aktivitäts-Feed, Album-Index, Zeitleisten-Seiten
  (Cursor nach Datum), alles aus dem NAS-Index. Zeitleiste unbedingt virtualisieren (84 k+ Medien).

## Design Tokens (shadcn/ui-Format)

```css
@layer base {
  :root {
    /* Pergament – helles Theme */
    --background: 44 47% 93%;        /* #F5F0E6 Rabenschwarz-Gegenstück */
    --foreground: 220 30% 6%;        /* #0B0D12 Pergament-Text */
    --card: 40 100% 99%;             /* #FFFDF8 */
    --card-foreground: 220 30% 6%;
    --popover: 40 100% 99%;
    --popover-foreground: 220 30% 6%;
    --primary: 35 79% 30%;           /* #8A5A10 Bernstein hell */
    --primary-foreground: 44 47% 93%;
    --secondary: 42 30% 87%;         /* #E8E1D2 Nachtblau-Gegenstück */
    --secondary-foreground: 220 30% 6%;
    --muted: 42 30% 87%;
    --muted-foreground: 220 12% 41%; /* #5B6475 Runensilber */
    --accent: 37 72% 42%;            /* #B7791F Goldlicht */
    --accent-foreground: 44 47% 93%;
    --destructive: 7 54% 40%;        /* #9E3B2F Runenrot */
    --destructive-foreground: 44 47% 93%;
    --border: 42 30% 87%;
    --input: 42 30% 87%;
    --ring: 37 72% 42%;
    --radius: 0.75rem;               /* 12 px */
  }

  .dark {
    /* Rabenschwarz – Standard */
    --background: 223 27% 6%;        /* #0B0D12 */
    --foreground: 42 38% 88%;        /* #EDE6D6 Pergament */
    --card: 222 40% 12%;             /* #121A2B Mitternacht */
    --card-foreground: 42 38% 88%;
    --popover: 222 40% 12%;
    --popover-foreground: 42 38% 88%;
    --primary: 38 74% 56%;           /* #E3A73B Bernstein */
    --primary-foreground: 223 27% 6%;/* Schrift auf Bernstein IMMER Rabenschwarz */
    --secondary: 221 39% 18%;        /* #1C2740 Nachtblau */
    --secondary-foreground: 42 38% 88%;
    --muted: 221 39% 18%;
    --muted-foreground: 216 12% 81%; /* #C8CDD6 Runensilber */
    --accent: 36 83% 71%;            /* #F4C878 Goldlicht */
    --accent-foreground: 223 27% 6%;
    --destructive: 6 51% 47%;        /* #B5483B Runenrot */
    --destructive-foreground: 42 38% 88%;
    --border: 221 39% 18%;
    --input: 221 39% 18%;
    --ring: 36 83% 71%;
  }
}
```

**Rohwerte (dunkel / hell)**

| Token | Dunkel | Hell | Einsatz |
|---|---|---|---|
| Rabenschwarz | `#0B0D12` | `#F5F0E6` | Hintergrund |
| Mitternacht | `#121A2B` | `#FFFDF8` | Karten, Leisten |
| Nachtblau | `#1C2740` | `#E8E1D2` | erhöhte Flächen, Hover |
| Bernstein | `#E3A73B` | `#8A5A10` | Buttons, Likes, aktive Elemente |
| Goldlicht | `#F4C878` | `#B7791F` | Fokus, Hervorhebungen |
| Runensilber | `#C8CDD6` | `#5B6475` | Sekundärtext, Icons |
| Pergament | `#EDE6D6` | `#0B0D12` | Primärtext |
| Runenrot | `#B5483B` | `#9E3B2F` | Fehler, Löschen |

**Typografie**
- **Cinzel** (500/600) ausschließlich für App-Name und große Titel (Rückblick-Titel 22–23 px,
  Seitentitel 22 px, Wortmarke 20 px / 0.15em).
- **Inter** (400/500/600/700) für alles andere. Skala: 10,5 · 11 · 11,5 · 12 · 12,5 · 13 · 13,5 · 14 px.
  Sektionslabels: 11 px, 600, `letter-spacing: 0.16em`, uppercase.
- **Material Symbols Rounded** für Icons (16 / 20 / 22 / 24 px; aktiv `FILL 1`).

**Radien:** 999 px (Chips/Pills) · 13 px (Logo-Kachel Desktop) · 12 px (`--radius`, Karten, Buttons,
Felder) · 11 px (Logo-Kachel mobil) · 8 px (Thumbnails) · 6 px (Zählchips) · 5 px (Badges) · 3 px (Griff).

**Abstände (Tailwind-Skala):** 2 px Fotoraster-Gap · 6/8/10/12 px Komponenten-Gaps · 14/16 px
Karten-Gaps Desktop · 20 px Seitenrand mobil · 28/32 px Seitenrand Desktop · 22–26 px zwischen Sektionen.

**Schatten:** Artboard `0 40px 90px rgba(0,0,0,.6)`; Bernstein-Griff-Glow
`0 0 14px rgba(244,200,120,.35)`; Overlays nutzen `backdrop-filter: blur(8–18px)`.

**Barrierefreiheit:** Textkontrast ≥ 4,5:1 (Runensilber auf Mitternacht = 8,9:1), Touch-Ziele ≥ 44 px,
Schrift auf Bernstein immer `#0B0D12`.

## Assets
- `assets/muninn-mark.png` – Rabenkopf/Signet, freigestellt (459 × 566, transparent), abgeleitet aus
  dem gelieferten Logo. Unverändert verwenden; wegen des dunklen Navy immer auf heller Fläche
  (Pergament-Kachel) platzieren.
- `assets/muninn-logo.png` – volle Wortbildmarke (1697 × 566, transparent) für Anmeldung/Splash.
- `uploads/logo.png` – Originaldatei des Kunden (weißer Hintergrund).
- Icons: **Material Symbols Rounded** (Google Fonts) – bevorzugt als lokal installiertes Paket.
- Schriften: **Cinzel** und **Inter** (Google Fonts).
- Fotos: sämtliche Bildflächen sind Farbverlaufs-Platzhalter, keine echten Medien.

## Files
- `Muninn Start Mobil Dunkel.dc.html` – der Entwurf (Mobil + Desktop nebeneinander auf einer
  Arbeitsfläche). Im Browser direkt zu öffnen; `support.js` gehört zur Vorschau-Laufzeit und ist
  **nicht** Teil der Implementierung.
- `support.js` – Laufzeit der Vorschau (nur damit die HTML-Datei lokal rendert).
- `assets/` – freigestellte Logodateien.
