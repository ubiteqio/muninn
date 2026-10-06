# Google Play listing

What the Play Console asks for, ready to paste. German is the default language, English the
second. The limits in brackets are Google's; `check_listing.py play-listing.md` counts them.

The **full description** [4000] is the App Store description, word for word: `de.description` and
`en.description` in [`listing.md`](listing.md). Neither text mentions a platform.

The images come from `node store/screenshots.mjs`, into `data/demo/shots/<language>/`:

| Play Console | File | Size |
| --- | --- | --- |
| App icon | `android-icon-512.png` (both languages) | 512 × 512 |
| Feature graphic | `android-feature-graphic.png` | 1024 × 500 |
| Phone screenshots | `android-phone-1…7-*.png` | 1080 × 1920 |
| 7-inch tablet screenshots | `android-7in-1…7-*.png` | 1200 × 1920 |
| 10-inch tablet screenshots | `android-10in-1…6-*.png` | 2560 × 1600, landscape |

## Deutsch (default)

### App-Name [30]

<!-- field: de.title -->
```
Muninn
```

### Kurzbeschreibung [80]

<!-- field: de.short -->
```
Jahrzehnte voller Familienfotos auf eurem NAS: privat, durchsuchbar, gemeinsam.
```

## English

### App name [30]

<!-- field: en.title -->
```
Muninn - The Raven
```

### Short description [80]

<!-- field: en.short -->
```
Decades of family photos on your NAS: private, searchable, shared with family.
```

## Store settings

| Field | Value |
| --- | --- |
| App or game | App |
| Category | Photography |
| Tags | Photo & video, Family, Photo storage (pick what the console offers) |
| Email address | required by Google, shown publicly: an address of your choice |
| Website | https://github.com/ubiteqio/muninn |
| Privacy policy | https://github.com/ubiteqio/muninn/blob/dev/PRIVACY.md |

## App content

- **App access:** "All or some functionality is restricted". Google's reviewer needs a server
  address and a demo account, the same blocker as Apple's review: a Muninn server reachable from
  the internet over HTTPS. Until it exists, the app can be prepared and tested internally but
  not reviewed.
- **Ads:** no ads.
- **Target audience:** 18 and over. The family's admin creates every account; choosing an age
  group under 13 would put the app under the Families policy, which a self-hosted client cannot
  meet in the way Google expects.
- **Content rating (IARC questionnaire):** category "Utility, productivity, communication or
  other". No violence, sexuality, language, drugs or gambling. Users can interact (comments)
  and share content (photos), but only within the family's own server. Expect a low rating with
  the note "Users interact".
- **Data safety:** our suggestion is **no data collected, no data shared**. The app sends data
  only to the server the family runs and chooses itself; nothing reaches the developers. Data is
  encrypted in transit when the server uses HTTPS, which is the user's setting, so answer that
  question with care. The map loads tiles from OpenFreeMap, which sees the IP address and the map
  area; this is covered in the privacy policy. Google decides what counts, so read its
  definitions once before submitting.
- **Government app, financial features, health, news:** no.
