import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import type { Memory } from '@/features/memories/use-memories'
import { cn } from '@/lib/utils'

/** The gradient that lifts the title off the photo, straight from the design. */
const SCRIM =
  'linear-gradient(180deg, rgba(11,13,18,.55) 0%, rgba(11,13,18,0) 34%, rgba(11,13,18,.1) 52%, rgba(11,13,18,.86) 100%)'

const DAY = new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'long', year: 'numeric' })

/** The picture on the card: the one with a person, a like or a star came first on the server. */
function coverOf(memory: Memory): string | null {
  const [first] = memory.media
  return first ? (first.urls.preview ?? first.urls.thumb) : null
}

/**
 * One look back: "Heute vor 5 Jahren", the album it is from, the day and how many photos.
 * The whole card starts the slideshow.
 */
export function MemoryCard({
  memory,
  onOpen,
  className,
}: {
  memory: Memory
  onOpen: () => void
  className?: string
}) {
  const { t } = useTranslation()
  const cover = coverOf(memory)
  const title = memory.title ?? String(memory.year)
  const tag = t(memory.from_week ? 'memories.weekAgo' : 'memories.yearsAgo', {
    count: memory.years_ago,
  })

  return (
    <button
      type="button"
      aria-label={t('memories.open', { title: `${tag}: ${title}` })}
      className={cn(
        'group relative block overflow-hidden rounded-lg bg-secondary text-left transition',
        'hover:ring-1 hover:ring-primary/35',
        className,
      )}
      onClick={onOpen}
    >
      {cover && (
        <img
          src={cover}
          alt=""
          loading="lazy"
          className="absolute inset-0 size-full object-cover transition duration-500 group-hover:scale-[1.03]"
        />
      )}
      <div aria-hidden="true" className="absolute inset-0" style={{ backgroundImage: SCRIM }} />

      <Badge variant="glass" className="absolute left-3 top-3">
        <Symbol name="history" size={15} className="text-[#E3A73B]" />
        {tag}
      </Badge>

      <div className="absolute inset-x-4 bottom-4">
        {/* On the photo, whatever the page's look: light text on the dark scrim. */}
        <h3 className="line-clamp-2 text-title font-semibold text-[#EDE6D6] lg:text-title-lg">
          {title}
        </h3>
        <p className="mt-1 text-sm text-[#C8CDD6]">
          {DAY.format(new Date(`${memory.taken_on}T12:00:00`))} ·{' '}
          {t('memories.photos', { count: memory.media.length })}
        </p>
      </div>
    </button>
  )
}
