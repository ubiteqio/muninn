import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyNote } from '@/components/muninn/empty-note'
import { SectionHeading } from '@/components/muninn/section-heading'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { MemoryCard } from '@/features/memories/memory-card'
import { type Memory, useMemories } from '@/features/memories/use-memories'
import { DESKTOP_QUERY, useMediaQuery } from '@/hooks/use-media-query'

/** How long each picture of a slideshow stays. */
const SLIDE_MS = 4500

/**
 * Rückblicke: the photos of this day in earlier years, one card per year.
 * Mobile: a horizontal snap scroller of 250 x 316 cards that bleeds into the page margin.
 * Desktop: a three column grid of 280 px high cards.
 */
export function MemoriesSection() {
  const { t } = useTranslation()
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const memories = useMemories()
  const [playing, setPlaying] = useState<Memory | null>(null)
  const [current, setCurrent] = useState<string | undefined>()

  const viewer = useMediaViewer(playing?.media ?? [], {
    current,
    onCurrentChange: (mediaId) => {
      setCurrent(mediaId)
      if (mediaId === undefined) setPlaying(null)
    },
    social: true,
    slideshow: SLIDE_MS,
  })

  const items = memories.data ?? []
  const play = (memory: Memory) => {
    setPlaying(memory)
    setCurrent(memory.media[0]?.id)
  }

  return (
    <section aria-labelledby="memories-heading">
      <SectionHeading title={t('memories.title')} className="px-5 lg:px-0" />

      {memories.isSuccess && items.length === 0 ? (
        <EmptyNote className="mx-5 lg:mx-0">{t('memories.empty')}</EmptyNote>
      ) : isDesktop ? (
        <div className="mt-4 grid grid-cols-3 gap-4">
          {items.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              className="h-[280px]"
              onOpen={() => {
                play(memory)
              }}
            />
          ))}
        </div>
      ) : (
        <div className="scroll-snap-x mt-3 flex scroll-px-5 gap-3 overflow-x-auto px-5">
          {items.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              className="h-[316px] w-[250px] shrink-0 snap-start"
              onOpen={() => {
                play(memory)
              }}
            />
          ))}
        </div>
      )}
      {viewer.panel}
    </section>
  )
}
