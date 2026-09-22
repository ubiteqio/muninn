import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { PageColumn } from '@/components/layout/page-column'
import { PageHeading } from '@/components/layout/page-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Card } from '@/components/ui/card'
import { type Report, useOverview } from '@/features/overview/use-overview'
import { Face } from '@/features/people/face'
import { cn } from '@/lib/utils'

const NUMBER = new Intl.NumberFormat('de-DE')
const DECIMAL = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 })

function bytes(value: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${DECIMAL.format(size)} ${units[unit] ?? 'B'}`
}

function hours(seconds: number): string {
  const total = Math.round(seconds / 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  return h > 0 ? `${String(h)} h ${String(m)} min` : `${String(m)} min`
}

function share(part: number, whole: number): number {
  return whole > 0 ? part / whole : 0
}

function percent(part: number, whole: number): string {
  return `${String(Math.round(share(part, whole) * 100))} %`
}

/**
 * Überblick: the library at a glance. Only counts and shares - how much there is, from when,
 * who and where - so the whole of it can be understood before anything is looked at in detail.
 * It also shows how far Muninn has got with it, and the housekeeping.
 */
export function OverviewScreen() {
  const { t } = useTranslation()
  const overview = useOverview()
  const data = overview.data

  return (
    <AppShell title={t('overview.title')} active="overview">
      <PageColumn className="space-y-5 px-5 md:px-0">
        <PageHeading title={t('overview.title')} description={t('overview.description')} />
        {overview.isPending && (
          <p className="text-base text-muted-foreground">{t('overview.loading')}</p>
        )}
        {overview.isError && (
          <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}
        {data && <ReportBody data={data} />}
      </PageColumn>
    </AppShell>
  )
}

function ReportBody({ data }: { data: Report }) {
  const { t } = useTranslation()
  const { totals } = data
  const from = totals.first_taken ? new Date(totals.first_taken).getFullYear() : null
  const until = totals.last_taken ? new Date(totals.last_taken).getFullYear() : null

  return (
    <div className="space-y-5">
      <section aria-label={t('overview.totals')} className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Tile
          icon="photo_library"
          value={NUMBER.format(totals.media)}
          label={t('overview.media')}
          note={t('overview.inAlbums', { count: totals.albums })}
        />
        <Tile
          icon="image_search"
          value={NUMBER.format(totals.photos)}
          label={t('overview.photos')}
        />
        <Tile
          icon="play_arrow"
          value={NUMBER.format(totals.videos)}
          label={t('overview.videos')}
          note={
            totals.videos > 0
              ? t('overview.videoLength', { length: hours(totals.video_seconds) })
              : undefined
          }
        />
        <Tile
          icon="download"
          value={bytes(totals.bytes)}
          label={t('overview.size')}
          note={
            totals.derived_bytes > 0
              ? t('overview.derivedSize', { size: bytes(totals.derived_bytes) })
              : undefined
          }
        />
      </section>

      <Section
        title={t('overview.years')}
        note={
          from && until ? t('overview.span', { from, until, count: until - from + 1 }) : undefined
        }
      >
        <YearChart years={data.years} />
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title={t('overview.pipeline')}>
          <ul className="space-y-3">
            {data.pipeline.map((step) => (
              <li key={step.step}>
                <Progress label={t(`overview.step.${step.step}`)} done={step.done} of={step.of} />
              </li>
            ))}
          </ul>
        </Section>

        <Section title={t('overview.content')}>
          <div className="grid grid-cols-2 gap-3">
            <Figure value={NUMBER.format(data.content.frames)} label={t('overview.frames')} />
            <Figure value={hours(data.content.spoken_seconds)} label={t('overview.spoken')} />
            <Figure
              value={NUMBER.format(data.content.videos_with_speech)}
              label={t('overview.withSpeech')}
            />
            <Figure value={NUMBER.format(data.content.with_text)} label={t('overview.withText')} />
            <Figure
              value={NUMBER.format(data.content.screenshots)}
              label={t('overview.screenshots')}
            />
            <Figure value={NUMBER.format(data.content.documents)} label={t('overview.documents')} />
          </div>
          <Bars
            items={data.times_of_day.map((item) => ({
              name: t(`overview.time.${item.name}`, item.name),
              count: item.count,
            }))}
            className="mt-5"
          />
        </Section>
      </div>

      <Section title={t('overview.motifs')}>
        <TagCloud tags={data.tags} />
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title={t('overview.people')}>
          <div className="flex flex-wrap items-center gap-6">
            <Ring
              parts={[
                {
                  value: data.people.named,
                  className: 'text-primary',
                  label: t('overview.named'),
                },
                {
                  value: data.people.suggested,
                  className: 'text-accent',
                  label: t('overview.suggested'),
                },
                {
                  value: data.people.unnamed - data.people.suggested,
                  className: 'text-muted-foreground/40',
                  label: t('overview.unnamed'),
                },
              ]}
              center={NUMBER.format(data.people.faces)}
              caption={t('overview.faces')}
            />
            <div className="space-y-1 text-base text-muted-foreground">
              <p>{t('overview.personsNamed', { count: data.people.persons })}</p>
              <p>{t('overview.groupsOpen', { count: data.people.groups })}</p>
              <p>
                {t('overview.withFaces', {
                  share: percent(data.people.media_with_faces, totals.media),
                })}
              </p>
            </div>
          </div>
          {data.persons.length > 0 && (
            <ul className="mt-5 grid grid-cols-4 gap-3 sm:grid-cols-6">
              {data.persons.map((person) => (
                <li key={person.id}>
                  <Link
                    to="/people/$personId"
                    params={{ personId: person.id }}
                    className="flex flex-col items-center gap-1 text-center"
                  >
                    <Face src={person.crop} size={52} />
                    <span className="w-full truncate text-sm text-foreground">{person.name}</span>
                    <span className="-mt-1 text-xs text-muted-foreground">
                      {NUMBER.format(person.media)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={t('overview.places')}>
          <div className="flex flex-wrap items-center gap-6">
            <Ring
              parts={[
                {
                  value: data.places.with_gps,
                  className: 'text-primary',
                  label: t('overview.withGps'),
                },
                {
                  value: data.places.estimated,
                  className: 'text-accent',
                  label: t('overview.estimated'),
                },
                {
                  value: totals.media - data.places.with_gps - data.places.estimated,
                  className: 'text-muted-foreground/40',
                  label: t('overview.noPlace'),
                },
              ]}
              center={percent(data.places.with_gps + data.places.estimated, totals.media)}
              caption={t('overview.located')}
            />
            <div className="space-y-1 text-base text-muted-foreground">
              <p>{t('overview.countries', { count: data.places.countries })}</p>
              <p>{t('overview.towns', { count: data.places.towns })}</p>
            </div>
          </div>
          <Bars
            items={data.towns.map((town) => ({ name: town.name, count: town.count }))}
            className="mt-5"
          />
        </Section>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section title={t('overview.dates')}>
          <Stack
            items={data.date_sources.map((item) => ({
              name: t(`overview.source.${item.name}`, item.name),
              count: item.count,
            }))}
          />
        </Section>
        <Section title={t('overview.cameras')}>
          <Bars items={data.cameras} />
        </Section>
        <Section title={t('overview.more')}>
          <div className="grid grid-cols-2 gap-3">
            <Figure
              value={NUMBER.format(data.duplicates.groups)}
              label={t('overview.duplicates')}
            />
            <Figure value={NUMBER.format(data.duplicates.hidden)} label={t('overview.hidden')} />
            <Figure value={NUMBER.format(data.social.reactions)} label={t('overview.reactions')} />
            <Figure value={NUMBER.format(data.social.comments)} label={t('overview.comments')} />
            <Figure value={NUMBER.format(data.social.favorites)} label={t('overview.favorites')} />
            <Figure value={NUMBER.format(data.social.users)} label={t('overview.users')} />
          </div>
        </Section>
      </div>
    </div>
  )
}

/** Every card the same shape: one figure, what it counts, and a quieter line of context. */
function Tile({
  icon,
  value,
  label,
  note,
}: {
  icon: string
  value: string
  label: string
  note?: string | undefined
}) {
  return (
    <Card className="p-4">
      <Symbol name={icon} size={20} className="text-primary" />
      <p className="mt-2 text-title font-semibold tabular-nums text-foreground">{value}</p>
      <p className="text-sm text-muted-foreground">{label}</p>
      {note && <p className="mt-0.5 text-xs-plus tabular-nums text-muted-foreground">{note}</p>}
    </Card>
  )
}

function Section({
  title,
  note,
  children,
}: {
  title: string
  note?: string | undefined
  children: ReactNode
}) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-section text-muted-foreground">
          {title}
        </h3>
        {note && <span className="text-sm text-muted-foreground">{note}</span>}
      </div>
      <div className="mt-4">{children}</div>
    </Card>
  )
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <p className="text-lg font-semibold tabular-nums text-foreground">{value}</p>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}

/** Photos and videos per year, one column each: the shape of 26 years at a glance. */
function YearChart({ years }: { years: Report['years'] }) {
  const { t } = useTranslation()
  if (years.length === 0) return null
  const first = years[0]?.year ?? 0
  const last = years.at(-1)?.year ?? first
  const byYear = new Map(years.map((row) => [row.year, row]))
  const all = Array.from({ length: last - first + 1 }, (_, index) => first + index)
  const highest = Math.max(1, ...years.map((row) => row.photos + row.videos))
  const labelEvery = all.length > 16 ? 5 : all.length > 8 ? 2 : 1

  return (
    <div>
      <div className="flex h-44 items-end gap-[3px]">
        {all.map((year) => {
          const row = byYear.get(year)
          const photos = row?.photos ?? 0
          const videos = row?.videos ?? 0
          return (
            <div
              key={year}
              title={t('overview.yearTip', { year, photos, videos })}
              className="group flex h-full flex-1 flex-col justify-end"
            >
              <div
                className="w-full rounded-t-sm bg-accent/80 group-hover:bg-accent"
                style={{ height: `${String((videos / highest) * 100)}%` }}
              />
              <div
                className={cn(
                  'w-full bg-primary/70 group-hover:bg-primary',
                  videos === 0 && 'rounded-t-sm',
                )}
                style={{ height: `${String((photos / highest) * 100)}%` }}
              />
            </div>
          )
        })}
      </div>
      <div className="mt-1.5 flex gap-[3px] text-2xs tabular-nums text-muted-foreground">
        {all.map((year) => (
          <span key={year} className="flex-1 text-center">
            {(year - first) % labelEvery === 0 ? `'${String(year).slice(2)}` : ''}
          </span>
        ))}
      </div>
      <div className="mt-3 flex gap-4 text-sm text-muted-foreground">
        <Legend className="bg-primary/70" label={t('overview.photos')} />
        <Legend className="bg-accent/80" label={t('overview.videos')} />
      </div>
    </div>
  )
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('size-2.5 rounded-sm', className)} />
      {label}
    </span>
  )
}

function Progress({ label, done, of }: { label: string; done: number; of: number }) {
  const complete = of > 0 && done >= of
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {complete ? (
            <Symbol
              name="check_circle"
              size={14}
              filled
              className="mr-1 align-[-2px] text-emerald-500"
            />
          ) : null}
          {NUMBER.format(done)} / {NUMBER.format(of)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full rounded-full', complete ? 'bg-emerald-500/80' : 'bg-primary')}
          style={{ width: `${String(share(done, of) * 100)}%` }}
        />
      </div>
    </div>
  )
}

function Bars({
  items,
  className,
}: {
  items: { name: string; count: number }[]
  className?: string
}) {
  const highest = Math.max(1, ...items.map((item) => item.count))
  if (items.length === 0) return null
  return (
    <ul className={cn('space-y-2', className)}>
      {items.map((item) => (
        <li
          key={item.name}
          className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm"
        >
          <span className="truncate text-foreground" title={item.name}>
            {item.name}
          </span>
          <span className="h-2 overflow-hidden rounded-full bg-secondary">
            <span
              className="block h-full rounded-full bg-primary/70"
              style={{ width: `${String((item.count / highest) * 100)}%` }}
            />
          </span>
          <span className="tabular-nums text-muted-foreground">{NUMBER.format(item.count)}</span>
        </li>
      ))}
    </ul>
  )
}

const STACK_COLOURS = [
  'bg-primary',
  'bg-accent',
  'bg-emerald-500/70',
  'bg-sky-500/70',
  'bg-muted-foreground/40',
]

/** One bar split by share - where the dates come from, and how much can be relied on. */
function Stack({ items }: { items: { name: string; count: number }[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0)
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-secondary">
        {items.map((item, index) => (
          <span
            key={item.name}
            title={`${item.name}: ${percent(item.count, total)}`}
            className={STACK_COLOURS[index % STACK_COLOURS.length]}
            style={{ width: `${String(share(item.count, total) * 100)}%` }}
          />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {items.map((item, index) => (
          <li key={item.name} className="flex items-center gap-2">
            <span
              className={cn(
                'size-2.5 shrink-0 rounded-sm',
                STACK_COLOURS[index % STACK_COLOURS.length],
              )}
            />
            <span className="flex-1 text-foreground">{item.name}</span>
            <span className="tabular-nums text-muted-foreground">{percent(item.count, total)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** A ring in shares, with the total in the middle. */
function Ring({
  parts,
  center,
  caption,
}: {
  parts: { value: number; className: string; label: string }[]
  center: string
  caption: string
}) {
  const total = parts.reduce((sum, part) => sum + Math.max(0, part.value), 0)
  const radius = 42
  const circumference = 2 * Math.PI * radius
  const lengths = parts.map((part) =>
    total > 0 ? (Math.max(0, part.value) / total) * circumference : 0,
  )
  // Each part starts where the ones before it end.
  const starts = lengths.map((_, index) => lengths.slice(0, index).reduce((a, b) => a + b, 0))
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="size-28 -rotate-90" aria-hidden="true">
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="12"
          className="stroke-secondary"
        />
        {parts.map((part, index) => {
          const length = lengths[index] ?? 0
          return (
            <circle
              key={part.label}
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              strokeWidth="12"
              stroke="currentColor"
              strokeDasharray={`${String(length)} ${String(circumference - length)}`}
              strokeDashoffset={-(starts[index] ?? 0)}
              className={part.className}
            />
          )
        })}
        <text
          x="50"
          y="50"
          textAnchor="middle"
          dominantBaseline="central"
          transform="rotate(90 50 50)"
          className="fill-foreground text-[15px] font-semibold"
        >
          {center}
        </text>
      </svg>
      <ul className="space-y-1 text-sm">
        <li className="text-xs uppercase tracking-section text-muted-foreground">{caption}</li>
        {parts.map((part) => (
          <li key={part.label} className="flex items-center gap-2">
            <span className={cn('size-2.5 rounded-full bg-current', part.className)} />
            <span className="text-foreground">{part.label}</span>
            <span className="tabular-nums text-muted-foreground">
              {NUMBER.format(Math.max(0, part.value))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** What the pictures show, the most frequent larger. */
function TagCloud({ tags }: { tags: { name: string; count: number }[] }) {
  const highest = Math.max(1, ...tags.map((tag) => tag.count))
  const lowest = Math.min(...tags.map((tag) => tag.count))
  return (
    <ul className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
      {tags.map((tag) => {
        const weight = highest === lowest ? 1 : (tag.count - lowest) / (highest - lowest)
        return (
          <li key={tag.name}>
            <Link
              to="/search"
              search={{ q: tag.name }}
              title={NUMBER.format(tag.count)}
              className="rounded-md px-1 text-foreground transition hover:text-accent"
              style={{ fontSize: `${String(13 + weight * 13)}px`, opacity: 0.6 + weight * 0.4 }}
            >
              {tag.name}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
