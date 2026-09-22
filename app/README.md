# Muninn app

One React codebase for the web, iOS and Android. Capacitor wraps the same build as the native apps.

```bash
pnpm install
pnpm dev          # http://localhost:5173, proxies /api to the server in Docker
pnpm test
pnpm lint && pnpm typecheck
pnpm cap:sync     # build and hand the result to the iOS and Android projects
pnpm exec cap open ios      # opens Xcode
pnpm exec cap open android  # opens Android Studio
```

## Layout

| Path                     | Contents                                                      |
| ------------------------ | ------------------------------------------------------------- |
| `src/routes/`            | TanStack Router routes                                        |
| `src/features/`          | One folder per domain: memories, activity, albums, timeline   |
| `src/components/ui/`     | shadcn/ui components                                          |
| `src/components/layout/` | App shell, header, navigation                                 |
| `src/components/muninn/` | Muninn's own building blocks: icons, knotwork, media surfaces |
| `src/i18n/`              | German is the source language                                 |
| `scripts/`               | `subset-icons.py` cuts the icon font down to the icons in use |

## Design

The start screen follows the handoff in `docs/design/startbildschirm/handoff.md`: dark
"Rabenschwarz" theme, Inter throughout and Material Symbols Rounded for icons. The tokens live in
`src/index.css` and are the ones shadcn/ui reads. Where the implementation departs from a handoff
on purpose - the single typeface does - it is written down in `docs/design/README.md`.

Photos are placeholders for now (`src/features/home/placeholder-data.ts`): albums and the timeline
arrive with milestone 2, the activity feed with milestone 5.
