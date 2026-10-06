# Datenschutz / Privacy

[Deutsch](#deutsch) · [English](#english)

## Deutsch

*Stand: 6. Oktober 2026*

Muninn ist eine Foto- und Videobibliothek, die eine Familie auf ihrer eigenen Hardware betreibt.
Die App für iPhone, iPad und Android ist nur die Oberfläche dazu: Sie verbindet sich mit dem
Muninn-Server, dessen Adresse ihr beim ersten Start eingebt, und mit keinem anderen.

### Was wir als Entwickler erhalten

Nichts. Die App schickt keine Daten an uns, an UBITEQ.io oder an Dritte, die für uns arbeiten.
Es gibt keine Analyse, kein Tracking, keine Werbung und keine Absturzberichte, die die App selbst
versendet.

### Was zwischen App und eurem Server läuft

Anmeldename, Passwort, Fotos, Videos, Kommentare, Reaktionen, Favoriten, Namen von Personen und
alles andere, was ihr in Muninn seht oder tut, liegt auf eurem eigenen Server und wird nur
zwischen ihm und der App übertragen. Wer diesen Server betreibt, ist für diese Daten
verantwortlich, in der Regel ihr selbst.

- **Anmeldung:** Die App speichert die Zugangsschlüssel (Tokens) für euren Server im
  geschützten Speicher des Geräts (iOS-Schlüsselbund, Android Keystore). Das Passwort selbst
  wird nicht auf dem Gerät gespeichert.
- **Fotomediathek:** Nur wenn ihr ein Bild ausdrücklich sichert, schreibt die App es in die
  Fotos des Geräts. Sie liest die Mediathek des Geräts nicht.
- **Lokales Netzwerk:** Die App darf Server im Heimnetz erreichen, weil Muninn dort meistens
  läuft.
- **Gesichter:** Die Gesichtserkennung läuft auf eurem Server und dem KI-Rechner, den ihr dafür
  einrichtet. Sie lässt sich in der Verwaltung abschalten, und alle Gesichtsdaten lassen sich
  dort auf einmal löschen.

### Die Karte

Die Kartenansicht lädt die Kartenkacheln von OpenFreeMap (openfreemap.org). Dabei erfährt
OpenFreeMap die IP-Adresse des Geräts und welchen Kartenausschnitt ihr gerade anseht, wie bei
jeder Karte im Web. Eure Fotos und deren Aufnahmeorte werden dabei nicht übertragen; die Punkte
auf der Karte kommen von eurem eigenen Server.

### Kinder

Muninn richtet sich an Familien. Konten legt der Verwalter des eigenen Servers an; die App
kennt keine eigene Registrierung.

### Kontakt

Fragen zum Datenschutz der App: über die Issues des Projekts auf GitHub,
<https://github.com/ubiteqio/muninn/issues>, oder an UBITEQ.io.

## English

*Last updated: 6 October 2026*

Muninn is a photo and video library that a family runs on its own hardware. The app for iPhone,
iPad and Android is only the window onto it: it connects to the Muninn server whose address you
enter on first launch, and to no other.

### What we, the developers, receive

Nothing. The app sends no data to us, to UBITEQ.io or to any third party working for us. There is
no analytics, no tracking, no advertising and no crash reporting sent by the app itself.

### What travels between the app and your server

Your username, password, photos, videos, comments, reactions, favourites, the names of people and
everything else you see or do in Muninn lives on your own server and is only sent between it and
the app. Whoever runs that server is responsible for that data, usually you.

- **Sign-in:** the app keeps the access tokens for your server in the device's protected storage
  (iOS Keychain, Android Keystore). The password itself is not stored on the device.
- **Photo library:** only when you explicitly save a picture does the app write it to the
  device's Photos. It does not read the device's photo library.
- **Local network:** the app may reach servers on your home network, because that is where
  Muninn usually runs.
- **Faces:** face recognition runs on your server and the AI machine you set up for it. It can be
  switched off in the admin area, where all face data can also be deleted at once.

### The map

The map view loads its map tiles from OpenFreeMap (openfreemap.org). Like any web map, this tells
OpenFreeMap the device's IP address and which part of the map you are looking at. Your photos and
where they were taken are not sent; the points on the map come from your own server.

### Children

Muninn is made for families. Accounts are created by whoever administers the family's own server;
the app has no sign-up of its own.

### Contact

Questions about the app's privacy: through the project's issues on GitHub,
<https://github.com/ubiteqio/muninn/issues>, or to UBITEQ.io.
