import { BookMap, type Point } from '@/features/photobooks/book-map'
import type { Leaf } from '@/features/photobooks/use-photobooks'
import { cn } from '@/lib/utils'

/** One picture as the server laid it out: where it is, how crooked, and how it is stuck down. */
interface Shown {
  id: string
  src: string
  tilt: number
  tape: string
  portrait: boolean
  video: boolean
  at: string
  caption?: string
}

/** Where a page sits in what is on screen. On a phone there is no right-hand page, only one. */
export type Side = 'left' | 'right' | 'single'

/**
 * One page of a photo book.
 *
 * The shapes come from the server - which pictures, in what arrangement, with what text - and
 * this draws them. Nothing is decided here beyond how a shape looks, so a book reads the same
 * on a phone, on a desktop and on paper.
 */
export function BookPage({ page, number, side }: { page: Leaf; number: number; side: Side }) {
  return (
    <section className={cn('page', side)}>
      {inside(page)}
      <span className="folio">{number}</span>
    </section>
  )
}

function inside(page: Leaf) {
  switch (String(page.kind)) {
    case 'auftakt':
      return (
        <div className="full">
          <Picture shown={shot(page.hero)} bare />
          <div className="over">
            <p className="kicker">{text(page.subtitle)}</p>
            <h1 className="headline" style={{ fontSize: 'clamp(34px, 6vmin, 76px)' }}>
              {text(page.title)}
            </h1>
            <p className="story">{text(page.route)}</p>
            <p className="caption">{text(page.counts)}</p>
          </div>
        </div>
      )

    case 'tag':
      return (
        <>
          <div className="behind">
            <Picture shown={shot(page.behind)} bare />
          </div>
          <div className="daypage">
            <p className="kicker">{text(page.note)}</p>
            <h2 className="day headline">{text(page.day)}</h2>
            <div className="rule" />
            <p className="story">
              {text(page.towns)}
              {text(page.doing) ? ` · ${text(page.doing)}` : ''}
            </p>
          </div>
        </>
      )

    case 'streifen':
      return (
        <>
          <Head page={page} />
          <div className="body">
            <div className="column">
              {shots(page.column).map((one) => (
                <Picture key={one.id} shown={one} />
              ))}
            </div>
            <div className="grow">
              <Picture shown={shot(page.hero)} fill />
              {shot(page.hero)?.caption ? (
                <p className="caption">{shot(page.hero)?.caption}</p>
              ) : null}
            </div>
          </div>
        </>
      )

    case 'karte':
      return (
        <>
          <BookMap points={points(page.points)} className="behindmap" />
          <div className="relative flex h-full flex-col gap-3.5">
            <Head page={page} />
            <div className="body">
              {shots(page.taped).map((one) => (
                <WithCaption key={one.id} shown={one} />
              ))}
            </div>
            <div className="strip">
              {shots(page.strip).map((one) => (
                <Picture key={one.id} shown={one} />
              ))}
            </div>
          </div>
        </>
      )

    case 'kontaktbogen':
      return (
        <>
          <Head page={page} />
          <div className="body" style={{ flexDirection: 'column' }}>
            <div className="grow">
              <Picture shown={shot(page.hero)} fill />
              {shot(page.hero)?.caption ? (
                <p className="caption">{shot(page.hero)?.caption}</p>
              ) : null}
            </div>
            <div className="sheet">
              {shots(page.sheet).map((one) => (
                <Picture key={one.id} shown={one} />
              ))}
            </div>
          </div>
        </>
      )

    case 'fundstueck':
      return (
        <>
          <Head page={page} />
          <div className="body">
            <div className="grow">
              <Picture shown={shot(page.picture)} fill />
            </div>
            <div className="flex w-[42%] flex-col justify-center gap-2">
              {lines(page.lines).map((line, at) =>
                at === 0 ? (
                  <p key={line} className="headline" style={{ fontSize: 'clamp(17px,2.2vmin,26px)' }}>
                    {line}
                  </p>
                ) : (
                  <p key={line} className="caption">
                    {line}
                  </p>
                ),
              )}
            </div>
          </div>
        </>
      )

    case 'doppelseite':
      return (
        <div className="full">
          <Picture shown={shot(page.picture)} bare />
          <div className="over">
            <p className="kicker">{text(page.note)}</p>
            <h2 className="headline" style={{ color: '#f6efe1' }}>
              {text(page.headline)}
            </h2>
            <p className="story">{text(page.story)}</p>
          </div>
        </div>
      )

    case 'schluss':
      return (
        <>
          <Head page={page} />
          <BookMap points={points(page.route)} whole className="worldmap" />
          <div className="stations">
            {stations(page.stations).map((station) => (
              <div key={station.name}>
                <b>{station.name}</b>
                {` · ${station.count} Aufnahmen`}
                {station.card?.where ? ` · ${station.card.where}` : ''}
                {station.card?.people ? ` · ${station.card.people}` : ''}
              </div>
            ))}
            {people(page.people).length > 0 ? (
              <div className="mt-1.5">Dabei: {people(page.people).join(', ')}</div>
            ) : null}
          </div>
        </>
      )

    default:
      return (
        <>
          <Head page={page} />
          <div
            className="two"
            style={{
              gridTemplateColumns: `repeat(${Math.min(shots(page.pictures).length, 2)}, 1fr)`,
            }}
          >
            {shots(page.pictures).map((one) => (
              <WithCaption key={one.id} shown={one} />
            ))}
          </div>
        </>
      )
  }
}

function Head({ page }: { page: Leaf }) {
  const card = page.card as { name: string; where: string; people: string } | null | undefined
  return (
    <div className="head">
      {text(page.note) ? <p className="kicker">{text(page.note)}</p> : null}
      {text(page.headline) ? <h2 className="headline">{text(page.headline)}</h2> : null}
      <div className="rule" />
      {text(page.story) ? <p className="story">{text(page.story)}</p> : null}
      {card ? (
        <p className="card">
          <b>{card.name}</b>
          {card.where ? ` · ${card.where}` : ''}
          {card.people ? <br /> : null}
          {card.people}
        </p>
      ) : null}
    </div>
  )
}

function Picture({
  shown,
  fill,
  bare,
}: {
  shown?: Shown | undefined
  fill?: boolean
  bare?: boolean
}) {
  if (!shown) return null
  const picture = (
    <img src={shown.src} alt="" loading="lazy" decoding="async" draggable={false} />
  )
  if (bare) return picture
  return (
    <div
      className={cn('photo', `tape-${shown.tape}`, fill && 'fill', shown.video && 'is-video')}
      style={{ transform: `rotate(${shown.tilt}deg)` }}
    >
      {picture}
    </div>
  )
}

function WithCaption({ shown }: { shown: Shown }) {
  return (
    <div className="grow">
      <Picture shown={shown} fill />
      {shown.caption || shown.at ? (
        <p className="caption">
          {shown.caption}
          {shown.caption && shown.at ? ' · ' : ''}
          {shown.at}
        </p>
      ) : null}
    </div>
  )
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function shot(value: unknown): Shown | undefined {
  return isShown(value) ? value : undefined
}

function shots(value: unknown): Shown[] {
  return Array.isArray(value) ? value.filter(isShown) : []
}

function isShown(value: unknown): value is Shown {
  return typeof value === 'object' && value !== null && 'src' in value && 'id' in value
}

function lines(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : []
}

function people(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : []
}

function points(value: unknown): Point[] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (one): one is Point =>
      typeof one === 'object' && one !== null && 'lat' in one && 'lon' in one,
  )
}

interface Station {
  name: string
  count: number
  card?: { name: string; where: string; people: string } | null
}

function stations(value: unknown): Station[] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (one): one is Station => typeof one === 'object' && one !== null && 'name' in one,
  )
}
