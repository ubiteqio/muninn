import { useNavigate } from '@tanstack/react-router'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { Knotwork } from '@/components/muninn/knotwork'
import { ActivitySection } from '@/features/activity/activity-section'
import { RecentAlbumsSection } from '@/features/albums/recent-albums-section'
import { MemoriesSection } from '@/features/memories/memories-section'
import { WalhallSection } from '@/features/social/walhall-section'
import { TimelineSection } from '@/features/timeline/timeline-section'
import type { Level } from '@/features/timeline/use-timeline'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'
import type { HomeSearch } from '@/routes'

/**
 * The start screen: memories to jog the memory, what the family has been up to, new albums and
 * the whole library as a timeline.
 *
 * Mobile keeps all four sections in one column. From 1024 px activity and albums move into the
 * aside, leaving memories and the timeline in the main column, as the design specifies.
 */
export function HomeScreen({
  view = 'years',
  at,
  medium,
}: {
  view?: Level | undefined
  at?: string | undefined
  medium?: string | undefined
}) {
  const { t } = useTranslation()
  const isWide = useMediaQuery(WIDE_QUERY)
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const navigate = useNavigate()

  // The picture on screen stands in the address, so it can be linked to and the back button
  // closes it. Opening is worth a history entry, moving on within the viewer is not.
  // Which level the timeline shows travels in the address as well. Stepping in is worth a
  // history entry: the back button then goes back up a level.
  const onLevelChange = useCallback(
    (level: Level, period: string | undefined) => {
      void navigate({
        to: '/home',
        search: (previous: HomeSearch) => {
          const next: HomeSearch = { ...previous }
          delete next.at
          delete next.medium
          next.view = level
          if (period !== undefined) next.at = period
          return next
        },
      })
    },
    [navigate],
  )

  const onMediumChange = useCallback(
    (mediaId: string | undefined) => {
      void navigate({
        to: '/home',
        search: (previous: HomeSearch) => {
          const next: HomeSearch = { ...previous }
          delete next.medium
          if (mediaId !== undefined) next.medium = mediaId
          return next
        },
        replace: mediaId === undefined || medium !== undefined,
      })
    },
    [medium, navigate],
  )

  const side = (
    <div className="space-y-6">
      <ActivitySection thumbSize={44} />
      <WalhallSection layout="grid" />
      <RecentAlbumsSection layout="grid" />
    </div>
  )

  return (
    <AppShell title={t('nav.home')} active="home" {...(isWide ? { aside: side } : {})}>
      <div className="space-y-6">
        <MemoriesSection />

        <Knotwork className={isWide ? '' : 'px-5'} />

        {/* Narrow screens keep both lists in the flow; wider ones show them in the aside. */}
        {!isWide && (
          <>
            <div className="px-5">
              <ActivitySection />
            </div>
            <WalhallSection />
            <RecentAlbumsSection />
            <Knotwork className="px-5" />
          </>
        )}

        <TimelineSection
          columns={isDesktop ? 8 : 3}
          level={view}
          at={at}
          onLevelChange={onLevelChange}
          medium={medium}
          onMediumChange={onMediumChange}
          className={isWide ? '' : 'px-5'}
        />
      </div>
    </AppShell>
  )
}
