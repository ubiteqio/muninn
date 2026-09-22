import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import {
  downloadHiddenList,
  type DuplicateGroup,
  type DuplicateState,
  useDuplicates,
  useKeep,
  useShowAgain,
} from '@/features/admin/use-duplicates'
import { formatBytes } from '@/features/media/format'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { cn } from '@/lib/utils'

/**
 * Doppelgänger: the same picture more than once - the same file in two folders, a smaller copy
 * from a messenger, the shots of a burst. Muninn suggests the one to keep; whatever is not kept
 * is hidden from albums, timeline, search and map. The NAS stays as it is: the paths of the
 * hidden copies come as a list, to delete there by hand if wanted.
 */
export function AdminDuplicatesPage() {
  const { t } = useTranslation()
  const [state, setState] = useState<DuplicateState>('open')
  const duplicates = useDuplicates(state)
  const [current, setCurrent] = useState<string | undefined>()
  const [downloadFailed, setDownloadFailed] = useState(false)

  const groups = duplicates.data?.pages.flatMap((page) => page.items) ?? []
  const openCount = duplicates.data?.pages[0]?.open_count ?? 0
  const media = groups.flatMap((group) => group.members.map((member) => member.media))
  const viewer = useMediaViewer(media, { current, onCurrentChange: setCurrent })

  return (
    <AdminArea section="duplicates">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t('admin.duplicates.title')}</h2>
          <p className="mt-1.5 max-w-2xl text-base text-muted-foreground">
            {t('admin.duplicates.description')}
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            setDownloadFailed(false)
            downloadHiddenList().catch(() => {
              setDownloadFailed(true)
            })
          }}
        >
          <Symbol name="download" size={20} />
          {t('admin.duplicates.download')}
        </Button>
      </div>
      {downloadFailed && (
        <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(['open', 'all'] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={state === value}
            className={cn(
              'rounded-full border px-3 py-1 text-sm-plus transition',
              state === value
                ? 'border-accent bg-accent/15 text-foreground'
                : 'border-hairline/10 text-muted-foreground hover:text-foreground',
            )}
            onClick={() => {
              setState(value)
            }}
          >
            {value === 'open'
              ? t('admin.duplicates.open', { count: openCount })
              : t('admin.duplicates.all')}
          </button>
        ))}
      </div>

      {duplicates.isPending && (
        <p className="text-base text-muted-foreground">{t('admin.duplicates.loading')}</p>
      )}
      {duplicates.isError && (
        <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
      )}
      {duplicates.isSuccess && groups.length === 0 && (
        <p className="py-8 text-center text-md text-muted-foreground">
          {t('admin.duplicates.none')}
        </p>
      )}

      <div className="space-y-4">
        {groups.map((group) => (
          <GroupCard key={group.id} group={group} onOpen={setCurrent} />
        ))}
      </div>

      {duplicates.hasNextPage && (
        <Button
          variant="outline"
          className="w-full"
          disabled={duplicates.isFetchingNextPage}
          onClick={() => void duplicates.fetchNextPage()}
        >
          {t(duplicates.isFetchingNextPage ? 'admin.duplicates.loading' : 'admin.duplicates.more')}
        </Button>
      )}
      {viewer.panel}
    </AdminArea>
  )
}

/**
 * One group: every copy side by side, the suggested one marked. What is ticked stays; the rest
 * is hidden with one click. Ticked from the start is whatever is shown now, or else the
 * suggestion.
 */
function GroupCard({
  group,
  onOpen,
}: {
  group: DuplicateGroup
  onOpen: (mediaId: string) => void
}) {
  const { t } = useTranslation()
  const keep = useKeep()
  const showAgain = useShowAgain()
  const [kept, setKept] = useState<Set<string>>(() => {
    const shown = group.members.filter((member) => !member.hidden)
    const anyHidden = shown.length < group.members.length
    return new Set(
      (anyHidden ? shown : group.members.filter((member) => member.best)).map(
        (member) => member.media.id,
      ),
    )
  })
  const hidesSomething = group.members.some(
    (member) => !member.hidden && !kept.has(member.media.id),
  )

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-md font-semibold text-foreground">
          {t(`admin.duplicates.kind.${group.kind}`)}
          <span className="ml-2 font-normal text-muted-foreground">
            {t('admin.duplicates.count', { count: group.members.length })}
          </span>
        </h3>
        <Button
          disabled={kept.size === 0 || !hidesSomething || keep.isPending}
          onClick={() => {
            keep.mutate({ groupId: group.id, keep: [...kept] })
          }}
        >
          {t('admin.duplicates.keep', { count: kept.size })}
        </Button>
      </div>

      <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {group.members.map((member) => {
          const medium = member.media
          const ticked = kept.has(medium.id)
          return (
            <li key={medium.id} className={cn('min-w-0', member.hidden && 'opacity-50')}>
              <button
                type="button"
                className="relative block aspect-square w-full overflow-hidden rounded-lg bg-secondary"
                aria-label={t('admin.duplicates.show', { name: medium.origin.filename })}
                onClick={() => {
                  onOpen(medium.id)
                }}
              >
                {medium.urls.thumb && (
                  <img src={medium.urls.thumb} alt="" className="size-full object-cover" />
                )}
                {member.best && (
                  <span className="absolute left-1.5 top-1.5 rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-accent-foreground">
                    {t('admin.duplicates.best')}
                  </span>
                )}
              </button>
              <div className="mt-1.5 flex items-start gap-2">
                {member.hidden ? (
                  <button
                    type="button"
                    className="text-sm-plus text-accent underline-offset-2 hover:underline"
                    disabled={showAgain.isPending}
                    onClick={() => {
                      showAgain.mutate(medium.id)
                    }}
                  >
                    {t('admin.duplicates.showAgain')}
                  </button>
                ) : (
                  <label className="flex min-w-0 cursor-pointer items-center gap-1.5 text-sm-plus text-foreground">
                    <input
                      type="checkbox"
                      className="size-4 accent-[hsl(var(--accent))]"
                      checked={ticked}
                      onChange={() => {
                        setKept((previous) => {
                          const next = new Set(previous)
                          if (next.has(medium.id)) next.delete(medium.id)
                          else next.add(medium.id)
                          return next
                        })
                      }}
                    />
                    {t('admin.duplicates.keepThis')}
                  </label>
                )}
              </div>
              <p
                className="mt-1 truncate text-sm text-muted-foreground"
                title={medium.origin.relative_path}
              >
                {medium.origin.relative_path}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                {medium.width && medium.height
                  ? `${String(medium.width)} × ${String(medium.height)} · `
                  : ''}
                {formatBytes(medium.origin.byte_size)}
              </p>
            </li>
          )
        })}
      </ul>
      {(keep.isError || showAgain.isError) && (
        <p className="mt-2 text-base text-destructive">{t('admin.duplicates.failed')}</p>
      )}
    </Card>
  )
}
