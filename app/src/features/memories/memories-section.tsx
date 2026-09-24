import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyNote } from '@/components/muninn/empty-note'
import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { MemoryCard } from '@/features/memories/memory-card'
import { type Memory, useMemories } from '@/features/memories/use-memories'
import { DESKTOP_QUERY, useMediaQuery } from '@/hooks/use-media-query'

/** How long each picture of a slideshow stays. */
const SLIDE_MS = 4500

/**
 * How many years are offered at once. More than this and the start screen is a wall of years
 * before one has seen a single photograph.
 */
const MOST = 3

/**
 * Rückblicke: the photos of this day in earlier years, one card per year.
 *
 * One row that is swiped through, on a phone and on a desktop alike: the years are a row one
 * walks along, not a grid one reads. Three across where there is room for three.
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

  const items = (memories.data ?? []).slice(0, MOST)
  const play = (memory: Memory) => {
    setPlaying(memory)
    setCurrent(memory.media[0]?.id)
  }

  return (
    <section aria-labelledby="memories-heading" aria-busy={memories.isPending}>
      <SectionHeading id="memories-heading" title={t('memories.title')} className="px-5 lg:px-0" />

      {memories.isPending ? (
        <MemoriesLoading desktop={isDesktop} />
      ) : memories.isSuccess && items.length === 0 ? (
        <EmptyNote className="mx-5 lg:mx-0">{t('memories.empty')}</EmptyNote>
      ) : (
        <div className="scroll-snap-x no-scrollbar mt-3 flex scroll-px-5 gap-3 overflow-x-auto px-5 lg:mt-4 lg:scroll-px-0 lg:gap-4 lg:px-0">
          {items.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              className="h-[316px] w-[250px] shrink-0 snap-start lg:h-[280px] lg:w-[calc((100%-2rem)/3)]"
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

/**
 * The cards of the years, in the shape they will have: three across on the desktop, a row that
 * runs off the edge on the phone. The section keeps its height, so the timeline under it does
 * not jump once the years are there.
 */
function MemoriesLoading({ desktop }: { desktop: boolean }) {
  const shapes = Array.from({ length: MOST }, (_, index) => (
    <Placeholder
      key={index}
      className={
        desktop
          ? 'h-[280px] w-[calc((100%-2rem)/3)] shrink-0 rounded-lg'
          : 'h-[316px] w-[250px] shrink-0 rounded-lg'
      }
    />
  ))

  return (
    <LoadingBody
      boxed={false}
      className="mt-3 flex gap-3 overflow-hidden px-5 lg:mt-4 lg:gap-4 lg:px-0"
    >
      {shapes}
    </LoadingBody>
  )
}
