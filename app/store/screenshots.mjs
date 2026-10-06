// The App Store screenshots, taken from the demo server (see demo/README.md).
//
//   node store/screenshots.mjs [scene ...]        from app/, with the demo stack running
//
// Takes each scene raw at the size Apple wants, for the iPhone 6.9" and the iPad 13", then puts
// it into a frame with a caption in German and in English. Everything lands in data/demo/shots/.
// Without names, every scene is taken.

import { chromium } from '@playwright/test'
import { mkdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const WEB = 'http://localhost:9190'
const API = 'http://localhost:8800/api/v1'
const DEMO = resolve('../data/demo')
const OUT = `${DEMO}/shots`
const USER = 'anna'
const PASSWORD = readFileSync(`${DEMO}/admin-password`, 'utf8').trim()

// Apple's sizes: 1320 x 2868 for the iPhone 6.9", 2064 x 2752 for the iPad 13".
const DEVICES = {
  iphone: { viewport: { width: 440, height: 956 }, scale: 3, mobile: true },
  ipad: { viewport: { width: 1032, height: 1376 }, scale: 2, mobile: true },
}

// The light theme ("Pergament"); the frame around each capture follows it.
const THEME = 'light'
const FRAME = {
  light: {
    background: 'radial-gradient(120% 70% at 50% 0%, #FFFDF8 0%, #F5F0E6 45%, #EDE6D6 100%)',
    title: '#121A2B',
    line: '#4A5163',
    accent: '#A8711A',
    shadow: 'rgba(18,26,43,.28)',
  },
  dark: {
    background: 'radial-gradient(120% 70% at 50% 0%, #1a2440 0%, #121A2B 38%, #0B0D12 100%)',
    title: '#EDE6D6',
    line: '#C8CDD6',
    accent: '#E3A73B',
    shadow: 'rgba(0,0,0,.6)',
  },
}[THEME]

const SANDBURG = '2009/2009-08 Sommerurlaub Ostsee/IMG_3360.JPG'

const SCENES = {
  home: {
    caption: {
      de: ['Heute vor 8 Jahren', 'Jeden Morgen kommt eine Erinnerung zurück.'],
      en: ['On this day', 'Every morning a memory comes back.'],
    },
    take: async (page) => {
      await page.goto(`${WEB}/home`)
    },
  },
  search: {
    caption: {
      de: ['Finden, wie man fragt', 'Ein Satz genügt, auch für Bilder ohne Beschriftung.'],
      en: ['Find it the way you’d ask', 'One sentence is enough, even for uncaptioned photos.'],
    },
    take: async (page) => {
      await page.goto(`${WEB}/search?q=${encodeURIComponent('Kinder bauen eine Sandburg')}`)
    },
  },
  viewer: {
    caption: {
      de: ['Gemeinsam erinnern', 'Herzen, Kommentare und Antworten für die ganze Familie.'],
      en: ['Remember together', 'Hearts, comments and replies for the whole family.'],
    },
    take: async (page, api) => {
      const medium = await api.medium(SANDBURG)
      await page.goto(`${WEB}/albums/${medium.album_id}?medium=${medium.id}`)
      await page.waitForTimeout(1500)
      // A tap shows the controls; a click would zoom into the picture.
      await page.touchscreen.tap(page.viewportSize().width / 2, page.viewportSize().height / 2)
      await page.getByRole('button', { name: 'Kommentare' }).last().click()
    },
  },
  albums: {
    caption: {
      de: ['Eure Ordner werden Alben', 'Direkt vom NAS, ohne Import und ohne Upload.'],
      en: ['Your folders become albums', 'Straight from your NAS, with no import or upload.'],
    },
    take: async (page, api) => {
      const medium = await api.medium(SANDBURG)
      await page.goto(`${WEB}/albums/${medium.album_id}`)
    },
  },
  people: {
    caption: {
      de: ['Einmal benannt, überall gefunden', 'Muninn erkennt Gesichter über die Jahre wieder.'],
      en: ['Name a face once', 'Muninn finds them again across the years.'],
    },
    take: async (page) => {
      await page.goto(`${WEB}/people`)
    },
  },
  map: {
    caption: {
      de: ['Wo das Leben stattfand', 'Jedes Foto mit Ort auf einer Karte.'],
      en: ['Where life happened', 'Every photo with a place, on one map.'],
    },
    take: async (page) => {
      await page.goto(`${WEB}/map`)
    },
  },
}

async function demoApi() {
  const login = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASSWORD, client: 'native' }),
  })
  const { access_token: token } = await login.json()
  const get = async (path) =>
    (await fetch(`${API}${path}`, { headers: { authorization: `Bearer ${token}` } })).json()
  let media
  return {
    medium: async (path) => {
      media ??= (await get('/media?limit=500')).items
      const found = media.find((m) => m.origin.relative_path === path)
      if (!found) throw new Error(`not in the demo library: ${path}`)
      return found
    },
  }
}

async function takeRaw(browser, device, names, api) {
  const { viewport, scale, mobile } = DEVICES[device]
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: scale,
    isMobile: mobile,
    hasTouch: true,
    locale: 'de-DE',
    timezoneId: 'Europe/Berlin',
    colorScheme: THEME,
  })
  // The app keeps its theme in this browser and is dark unless told otherwise.
  await context.addInitScript((theme) => {
    localStorage.setItem('muninn.theme', theme)
  }, THEME)
  const page = await context.newPage()
  await page.goto(WEB)
  await page.fill('input[name=username]', USER)
  await page.fill('input[name=password]', PASSWORD)
  await page.keyboard.press('Enter')
  await page.waitForURL('**/home')
  for (const name of names) {
    await SCENES[name].take(page, api)
    await page.waitForLoadState('networkidle')
    // Previews fade in and the map settles; a quiet moment more keeps the capture calm.
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${OUT}/raw/${device}-${name}.png` })
    console.log(`raw ${device} ${name}`)
  }
  await context.close()
}

// A page set from a string may not load local files, so the font and the capture travel inside it.
const dataUrl = (path, type) => `data:${type};base64,${readFileSync(path).toString('base64')}`
const FONT = dataUrl(
  'node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2',
  'font/woff2',
)

function frameHtml(device, name, language) {
  const [title, line] = SCENES[name].caption[language]
  const raw = dataUrl(`${OUT}/raw/${device}-${name}.png`, 'image/png')
  const phone = device === 'iphone'
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face { font-family: Inter; src: url(${FONT}); }
  html, body { margin: 0; width: 100%; height: 100%; }
  body {
    background: ${FRAME.background};
    color: ${FRAME.title}; font-family: Inter, system-ui, sans-serif;
    display: flex; flex-direction: column; align-items: center; overflow: hidden;
  }
  .caption { text-align: center; padding: ${phone ? '150px 90px 0' : '130px 160px 0'}; }
  .step { color: ${FRAME.accent}; font-weight: 600; letter-spacing: .28em; font-size: 34px; text-transform: uppercase; }
  h1 { margin: ${phone ? 26 : 22}px 0 0; font-size: ${phone ? 96 : 92}px; line-height: 1.05; font-weight: 700; letter-spacing: -.02em; }
  p { margin: ${phone ? 30 : 24}px 0 0; font-size: ${phone ? 46 : 44}px; line-height: 1.3; color: ${FRAME.line}; font-weight: 400; }
  .screen {
    margin-top: ${phone ? 110 : 90}px; width: ${phone ? 1060 : 1700}px;
    border-radius: ${phone ? 72 : 44}px; overflow: hidden; flex: none;
    box-shadow: 0 0 0 ${phone ? 14 : 12}px #1d2433, 0 0 0 ${phone ? 16 : 14}px #2c3446, 0 60px 140px ${FRAME.shadow};
  }
  .screen img { display: block; width: 100%; }
  </style></head><body>
  <div class="caption"><div class="step">Muninn</div><h1>${title}</h1><p>${line}</p></div>
  <div class="screen"><img src="${raw}"></div>
  </body></html>`
}

async function frame(browser, device, names) {
  // The frame is drawn in real pixels: one CSS pixel is one pixel of the finished image.
  const { viewport, scale } = DEVICES[device]
  const size = { width: viewport.width * scale, height: viewport.height * scale }
  const page = await browser.newPage({ viewport: size, deviceScaleFactor: 1 })
  for (const language of ['de', 'en']) {
    mkdirSync(`${OUT}/${language}`, { recursive: true })
    for (const name of names) {
      const index = Object.keys(SCENES).indexOf(name) + 1
      await page.setContent(frameHtml(device, name, language), { waitUntil: 'load' })
      await page.evaluate(() => document.fonts.ready)
      await page.screenshot({ path: `${OUT}/${language}/${device}-${index}-${name}.png` })
    }
  }
  await page.close()
  console.log(`framed ${device}`)
}

const names = process.argv.length > 2 ? process.argv.slice(2) : Object.keys(SCENES)
mkdirSync(`${OUT}/raw`, { recursive: true })
const browser = await chromium.launch()
const api = await demoApi()
for (const device of Object.keys(DEVICES)) {
  await takeRaw(browser, device, names, api)
  await frame(browser, device, names)
}
await browser.close()
