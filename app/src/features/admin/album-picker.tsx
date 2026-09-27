import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { type Album, useAlbumTree } from '@/features/albums/use-albums'
import { cn } from '@/lib/utils'

/**
 * Walking the albums and ticking the ones a book is made of.
 *
 * A list of every folder in the library is no help when there are six hundred of them, and a
 * book is often several folders anyway - a holiday split into days, a year kept month by month.
 * So this walks the tree the way the album screen does: one level at a time, a tick beside each
 * folder, and "mit Unterordnern" for the common case of taking a branch whole.
 *
 * The order in which they were ticked is kept: the first one is where the book will hang.
 */
export function AlbumPicker({
  chosen,
  onChange,
}: {
  chosen: string[]
  onChange: (chosen: string[]) => void
}) {
  const { t } = useTranslation()
  const tree = useAlbumTree()
  const [at, setAt] = useState<string | null>(null)

  const byId = tree.data?.byId
  const here = at === null ? undefined : byId?.get(at)
  const folders = tree.data?.children.get(at) ?? []
  const path = useMemo(() => {
    const steps: Album[] = []
    let current = here
    while (current) {
      steps.unshift(current)
      current = current.parent_id ? byId?.get(current.parent_id) : undefined
    }
    return steps
  }, [byId, here])

  // A folder means everything in it: the server walks down from what is ticked, so a year
  // that holds its months is a book of those months.
  const pick = (album: Album) => {
    onChange(
      chosen.includes(album.id)
        ? chosen.filter((id) => id !== album.id)
        : [...chosen, album.id],
    )
  }

  return (
    <div className="rounded-lg border border-hairline/10 bg-card">
      {/* Where one stands, and the way back up. */}
      <div className="flex flex-wrap items-center gap-1 border-b border-hairline/10 px-3 py-2 text-xs-plus">
        <Step label={t('admin.photobooks.library')} onClick={() => { setAt(null) }} last={path.length === 0} />
        {path.map((step, index) => (
          <Step
            key={step.id}
            label={step.title}
            last={index === path.length - 1}
            onClick={() => { setAt(step.id) }}
          />
        ))}
      </div>

      <ul className="max-h-[280px] overflow-y-auto p-1.5">
        {tree.isPending && (
          <li className="px-2 py-1.5 text-base text-muted-foreground">{t('common.loading')}</li>
        )}
        {!tree.isPending && folders.length === 0 && (
          <li className="px-2 py-1.5 text-base text-muted-foreground">
            {t('admin.photobooks.noFolders')}
          </li>
        )}
        {folders.map((album) => {
          const inside = tree.data?.children.get(album.id)?.length ?? 0
          const pictures = withBelow(album, tree.data?.children)
          const ticked = chosen.includes(album.id)
          return (
            <li key={album.id} className="flex items-center gap-1">
              <button
                type="button"
                aria-pressed={ticked}
                className={cn(
                  'flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-base transition hover:bg-secondary/60',
                  ticked && 'text-foreground',
                )}
                onClick={() => {
                  pick(album)
                }}
              >
                <Symbol
                  name={ticked ? 'check_circle' : 'folder'}
                  size={18}
                  filled={ticked}
                  className={ticked ? 'text-primary' : 'text-muted-foreground'}
                />
                <span className="min-w-0 flex-1 truncate">{album.title}</span>
                <span className="shrink-0 tabular-nums text-xs-plus text-muted-foreground">
                  {pictures}
                </span>
              </button>

              {inside > 0 && (
                <button
                  type="button"
                  aria-label={t('admin.photobooks.open', { name: album.title })}
                  className="grid size-8 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-secondary/60 hover:text-foreground"
                  onClick={() => {
                    setAt(album.id)
                  }}
                >
                  <Symbol name="chevron_right" size={18} />
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** What a book of this folder would draw on: its own pictures and those of every folder in it. */
export function withBelow(album: Album, children: Map<string | null, Album[]> | undefined): number {
  const below = children?.get(album.id) ?? []
  return album.media_count + below.reduce((all, one) => all + withBelow(one, children), 0)
}

function Step({
  label,
  last,
  onClick,
}: {
  label: string
  last: boolean
  onClick: () => void
}) {
  return (
    <>
      <button
        type="button"
        disabled={last}
        className={cn(
          'max-w-[160px] truncate rounded px-1 py-0.5',
          last ? 'font-medium text-foreground' : 'text-muted-foreground hover:text-foreground',
        )}
        onClick={onClick}
      >
        {label}
      </button>
      {!last && <span className="text-muted-foreground">›</span>}
    </>
  )
}
