import { Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { EmptyNote } from '@/components/muninn/empty-note'
import { Placeholder } from '@/components/muninn/placeholder'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { MediaGrid, MediaGridLoading } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { Face } from '@/features/people/face'
import { NameDialog } from '@/features/people/name-dialog'
import { useGroupFaces, useGroupMedia, useNameGroup, usePeople } from '@/features/people/use-people'
import { useSearchAbilities } from '@/features/search/use-search'
import { useSocialUpdates } from '@/features/social/use-social'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'

/** How many of the group's faces stand at the top of the page. */
const HEADER_FACES = 6

/**
 * An unnamed group laid out like an album: every photo its faces are in, to see who it is
 * before giving it a name. Naming it here leads on to the person it became.
 */
export function GroupScreen({ cluster }: { cluster: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const isWide = useMediaQuery(WIDE_QUERY)
  const faces = useGroupFaces(cluster)
  const media = useGroupMedia(cluster)
  const people = usePeople()
  const name = useNameGroup()
  const [naming, setNaming] = useState(false)
  const [current, setCurrent] = useState<string | undefined>()
  const abilities = useSearchAbilities()
  const pictures = abilities.data?.pictures ?? false
  const viewer = useMediaViewer(media.media, {
    // The viewer builds its buttons when it opens, so it waits until "Ähnliche Bilder" is decided.
    current: abilities.isPending ? undefined : current,
    onCurrentChange: setCurrent,
    social: true,
    onSimilar: pictures
      ? (mediaId: string) => {
          void navigate({ to: '/search', search: { similar: mediaId } })
        }
      : undefined,
  })
  useSocialUpdates()

  const all = faces.data ?? []
  const columns = isDesktop ? 6 : isWide ? 5 : 3
  // Named since, by somebody else or in another tab: its faces have a person now.
  const gone = faces.isSuccess && all.length === 0

  return (
    <AppShell title={t('people.whoIsThis')} active="people">
      <div className="space-y-6 px-5 md:px-0">
        <Link
          to="/people"
          className="inline-flex items-center gap-1 text-sm-plus text-muted-foreground hover:text-foreground"
        >
          <Symbol name="arrow_back" size={18} />
          {t('people.title')}
        </Link>

        {(faces.isError || media.isError) && (
          <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}

        <header className="flex flex-wrap items-center gap-5">
          <div className="flex -space-x-3">
            {faces.isPending
              ? Array.from({ length: 4 }, (_, index) => (
                  <Placeholder
                    key={index}
                    className="size-16 rounded-full ring-2 ring-background"
                  />
                ))
              : all
                  .slice(0, HEADER_FACES)
                  .map((face) => (
                    <Face
                      key={face.id}
                      src={face.crop}
                      size={64}
                      className="ring-2 ring-background"
                    />
                  ))}
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-title font-semibold text-foreground">
              {t('people.whoIsThis')}
            </h1>
            {faces.isPending ? (
              <Placeholder className="mt-2 h-4 w-24" />
            ) : (
              <p className="mt-1 text-base text-muted-foreground">
                {t('people.faces', { count: all.length })}
              </p>
            )}
          </div>
          <Button
            disabled={all.length === 0}
            onClick={() => {
              setNaming(true)
            }}
          >
            {t('people.nameThem')}
          </Button>
        </header>

        {gone && <EmptyNote>{t('people.groupGone')}</EmptyNote>}

        {media.isPending && <MediaGridLoading columns={columns} />}

        {media.media.length > 0 && (
          <MediaGrid
            media={media.media}
            columns={columns}
            onOpen={(index) => {
              setCurrent(media.media[index]?.id)
            }}
            onEndReached={() => {
              if (media.hasNextPage && !media.isFetchingNextPage) void media.fetchNextPage()
            }}
          />
        )}
      </div>

      {naming && (
        <NameDialog
          open={naming}
          onOpenChange={setNaming}
          title={t('people.whoIsThis')}
          faces={all.map((face) => ({ id: face.id, crop: face.crop }))}
          persons={people.data?.persons ?? []}
          pending={name.isPending}
          failed={name.isError}
          onName={(value) => {
            name.mutate(
              { cluster, name: value },
              {
                onSuccess: (person) => {
                  setNaming(false)
                  void navigate({ to: '/people/$personId', params: { personId: person.id } })
                },
              },
            )
          }}
        />
      )}
      {viewer.panel}
    </AppShell>
  )
}
