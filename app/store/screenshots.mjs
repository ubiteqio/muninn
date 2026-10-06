// The store screenshots and graphics, taken from the demo server (see demo/README.md).
//
//   node store/screenshots.mjs [device ...] [scene ...] [graphics]   from app/, demo stack running
//
// Takes each scene raw in the device's window, then puts it into a frame of the size the store
// wants, with a caption in German and in English: the iPhone 6.9" and iPad 13" for Apple, a
// phone and 7" and 10" tablets for Google Play. "graphics" adds Google Play's feature graphic
// and icon. Everything lands in data/demo/shots/. Without names, every device and scene is taken.

import { chromium } from '@playwright/test'
import { mkdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const WEB = 'http://localhost:9190'
const API = 'http://localhost:8800/api/v1'
const DEMO = resolve('../data/demo')
const OUT = `${DEMO}/shots`
const USER = 'anna'
const PASSWORD = readFileSync(`${DEMO}/admin-password`, 'utf8').trim()
const LANGUAGES = ['de', 'en']

// window: the browser window the app is taken in. size: the finished image the store wants.
// layout: the caption and the screen inside that image, in its pixels.
//   Apple: 1320 x 2868 for the iPhone 6.9", 2064 x 2752 for the iPad 13".
//   Google: at most twice as long as wide; 9:16 for the phone and the 7" tablet, 16:10 for the
//   10" tablet.
const DEVICES = {
  iphone: {
    window: { width: 440, height: 956, scale: 3 },
    size: { width: 1320, height: 2868 },
    layout: {
      pad: '150px 90px 0',
      step: 34,
      title: 96,
      line: 46,
      gap: 110,
      screen: 1060,
      radius: 72,
      ring: 14,
    },
  },
  ipad: {
    window: { width: 1032, height: 1376, scale: 2 },
    size: { width: 2064, height: 2752 },
    layout: {
      pad: '130px 160px 0',
      step: 34,
      title: 92,
      line: 44,
      gap: 90,
      screen: 1700,
      radius: 44,
      ring: 12,
    },
  },
  'android-phone': {
    window: { width: 412, height: 800, scale: 3 },
    size: { width: 1080, height: 1920 },
    layout: {
      pad: '110px 70px 0',
      step: 26,
      title: 76,
      line: 36,
      gap: 70,
      screen: 780,
      radius: 52,
      ring: 12,
    },
  },
  'android-7in': {
    window: { width: 600, height: 900, scale: 2 },
    size: { width: 1200, height: 1920 },
    layout: {
      pad: '110px 90px 0',
      step: 26,
      title: 78,
      line: 36,
      gap: 70,
      screen: 900,
      radius: 40,
      ring: 12,
    },
  },
  // Lying on its side: upright, at 800 wide, a panel covers the picture instead of standing
  // beside it.
  'android-10in': {
    window: { width: 1280, height: 800, scale: 2 },
    size: { width: 2560, height: 1600 },
    layout: {
      pad: '100px 160px 0',
      step: 30,
      title: 84,
      line: 40,
      gap: 60,
      screen: 1880,
      radius: 40,
      ring: 14,
    },
  },
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

// A tap shows the viewer's controls. It lands on the dark band above the picture: on the picture
// itself, some widths take it as a request to zoom in.
const showControls = (page) =>
  page.touchscreen.tap(page.viewportSize().width / 2, page.viewportSize().height * 0.12)

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
      await page.goto(`${WEB}/search?q=${encodeURIComponent('Kinder am Strand')}`)
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
      await showControls(page)
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
  details: {
    caption: {
      de: ['Jedes Foto beschrieben', 'Wer darauf ist, was passiert und wo, ganz von selbst.'],
      en: ['Every photo described', 'Who is in it, what happens and where, all by itself.'],
    },
    take: async (page, api) => {
      const medium = await api.medium(SANDBURG)
      await page.goto(`${WEB}/albums/${medium.album_id}?medium=${medium.id}`)
      await page.waitForTimeout(1500)
      await showControls(page)
      await page.getByRole('button', { name: 'Details anzeigen' }).last().click()
    },
  },
  people: {
    // On the large tablets, six people leave the page mostly empty; the details carry the faces.
    devices: ['iphone', 'android-phone', 'android-7in'],
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

const shows = (name, device) => !SCENES[name].devices || SCENES[name].devices.includes(device)

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
  const { width, height, scale } = DEVICES[device].window
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: scale,
    isMobile: true,
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
  for (const name of names.filter((n) => shows(n, device))) {
    await SCENES[name].take(page, api)
    await page.waitForLoadState('networkidle')
    // Previews fade in and the map settles; a quiet moment more keeps the capture calm.
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${OUT}/raw/${device}-${name}.png` })
    console.log(`raw ${device} ${name}`)
  }
  await context.close()
}

// A page set from a string may not load local files, so the font and the images travel inside it.
const dataUrl = (path, type) => `data:${type};base64,${readFileSync(path).toString('base64')}`
const FONT = dataUrl(
  'node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2',
  'font/woff2',
)
const BASE_CSS = `
  @font-face { font-family: Inter; src: url(${FONT}); }
  html, body { margin: 0; width: 100%; height: 100%; }
  body { background: ${FRAME.background}; color: ${FRAME.title}; font-family: Inter, system-ui, sans-serif; overflow: hidden; }`

function frameHtml(device, name, language) {
  const [title, line] = SCENES[name].caption[language]
  const raw = dataUrl(`${OUT}/raw/${device}-${name}.png`, 'image/png')
  const l = DEVICES[device].layout
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}
  body { display: flex; flex-direction: column; align-items: center; }
  .caption { text-align: center; padding: ${l.pad}; }
  .step { color: ${FRAME.accent}; font-weight: 600; letter-spacing: .28em; font-size: ${l.step}px; text-transform: uppercase; }
  h1 { margin: ${Math.round(l.title * 0.26)}px 0 0; font-size: ${l.title}px; line-height: 1.05; font-weight: 700; letter-spacing: -.02em; }
  p { margin: ${Math.round(l.line * 0.62)}px 0 0; font-size: ${l.line}px; line-height: 1.3; color: ${FRAME.line}; font-weight: 400; }
  .screen {
    margin-top: ${l.gap}px; width: ${l.screen}px;
    border-radius: ${l.radius}px; overflow: hidden; flex: none;
    box-shadow: 0 0 0 ${l.ring}px #1d2433, 0 0 0 ${l.ring + 2}px #2c3446, 0 60px 140px ${FRAME.shadow};
  }
  .screen img { display: block; width: 100%; }
  </style></head><body>
  <div class="caption"><div class="step">Muninn</div><h1>${title}</h1><p>${line}</p></div>
  <div class="screen"><img src="${raw}"></div>
  </body></html>`
}

async function frame(browser, device, names) {
  // The frame is drawn in real pixels: one CSS pixel is one pixel of the finished image.
  const page = await browser.newPage({ viewport: DEVICES[device].size, deviceScaleFactor: 1 })
  const order = Object.keys(SCENES).filter((n) => shows(n, device))
  for (const language of LANGUAGES) {
    mkdirSync(`${OUT}/${language}`, { recursive: true })
    for (const name of names.filter((n) => shows(n, device))) {
      const index = order.indexOf(name) + 1
      await page.setContent(frameHtml(device, name, language), { waitUntil: 'load' })
      await page.evaluate(() => document.fonts.ready)
      await page.screenshot({ path: `${OUT}/${language}/${device}-${index}-${name}.png` })
    }
  }
  await page.close()
  console.log(`framed ${device}`)
}

// Google Play's feature graphic: the logo and one line on parchment, beside a few demo photos.
const FEATURE_PHOTOS = [
  '2018/2018-10 Herbst an der Müritz/DSC03666.JPG',
  SANDBURG,
  '2021/2021-04 Die Katzen ziehen ein/IMG_3777.JPG',
]
const FEATURE_TEXT = {
  de: ['Eure Familienfotos.', 'Privat, bei euch zu Hause.'],
  en: ['Your family photos.', 'Private, in your own home.'],
}

function featureHtml(language) {
  const [first, second] = FEATURE_TEXT[language]
  const logo = dataUrl('public/muninn-logo.png', 'image/png')
  const photos = FEATURE_PHOTOS.map((p) => dataUrl(`${DEMO}/library/${p}`, 'image/jpeg'))
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}
  .text { position: absolute; left: 64px; top: 0; bottom: 0; width: 500px; display: flex; flex-direction: column; justify-content: center; }
  .text img { width: 300px; display: block; }
  h1 { margin: 34px 0 0; font-size: 36px; line-height: 1.18; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; }
  h1 span { display: block; color: ${FRAME.accent}; }
  .photo { position: absolute; object-fit: cover; border: 7px solid #fff; border-radius: 6px; box-shadow: 0 18px 40px ${FRAME.shadow}; }
  .a { left: 585px; top: 48px; width: 260px; height: 180px; transform: rotate(-5deg); }
  .c { left: 812px; top: 58px; width: 160px; height: 124px; transform: rotate(7deg); }
  .b { left: 650px; top: 228px; width: 310px; height: 212px; transform: rotate(2deg); }
  </style></head><body>
  <div class="text"><img src="${logo}" alt=""><h1>${first}<span>${second}</span></h1></div>
  <img class="photo a" src="${photos[0]}"><img class="photo c" src="${photos[2]}"><img class="photo b" src="${photos[1]}">
  </body></html>`
}

async function graphics(browser) {
  const page = await browser.newPage({
    viewport: { width: 1024, height: 500 },
    deviceScaleFactor: 1,
  })
  for (const language of LANGUAGES) {
    await page.setContent(featureHtml(language), { waitUntil: 'load' })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: `${OUT}/${language}/android-feature-graphic.png` })
  }
  // The icon is the app's own, the raven on parchment; Google rounds the corners itself.
  const icon = dataUrl(
    'ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png',
    'image/png',
  )
  await page.setViewportSize({ width: 512, height: 512 })
  await page.setContent(
    `<html><body style="margin:0"><img src="${icon}" style="width:512px;height:512px;display:block"></body></html>`,
  )
  await page.screenshot({ path: `${OUT}/android-icon-512.png` })
  await page.close()
  console.log('graphics')
}

const args = process.argv.slice(2)
const devices = args.filter((a) => a in DEVICES)
const scenes = args.filter((a) => a in SCENES)
const withGraphics = args.length === 0 || args.includes('graphics')
const onlyGraphics = args.length > 0 && devices.length === 0 && scenes.length === 0

mkdirSync(`${OUT}/raw`, { recursive: true })
for (const language of LANGUAGES) mkdirSync(`${OUT}/${language}`, { recursive: true })
const browser = await chromium.launch()
if (!onlyGraphics) {
  const api = await demoApi()
  const names = scenes.length > 0 ? scenes : Object.keys(SCENES)
  for (const device of devices.length > 0 ? devices : Object.keys(DEVICES)) {
    await takeRaw(browser, device, names, api)
    await frame(browser, device, names)
  }
}
if (withGraphics) await graphics(browser)
await browser.close()
