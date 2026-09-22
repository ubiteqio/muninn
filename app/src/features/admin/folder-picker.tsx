import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Toggle } from '@/components/muninn/toggle'
import { Button } from '@/components/ui/button'
import { type FolderEntry, useExclusion, useFolders } from '@/features/admin/use-library'
import { cn } from '@/lib/utils'

/**
 * Walking through what the host has mounted.
 *
 * Muninn does not connect to anything itself: the host mounts the share, and this picker shows
 * what lies below the mount. A folder that is a mount of its own is usually exactly the share
 * somebody is looking for, so it says so.
 */
function ChooseButton({
  entry,
  label,
  indexedLabel,
  onChoose,
  insideExcluded = false,
}: {
  entry: FolderEntry
  label: string
  indexedLabel: string
  onChoose: (entry: FolderEntry) => void
  /** The folder around it is switched off, so this one cannot be switched on alone. */
  insideExcluded?: boolean
}) {
  // Inside a published folder, a subfolder is switched off and on instead of published.
  if (entry.publication_id && !entry.is_publication) {
    return <PublishedSwitch entry={entry} disabled={insideExcluded} />
  }
  return (
    <Button
      variant="outline"
      disabled={entry.published}
      onClick={() => {
        onChoose(entry)
      }}
    >
      {entry.published ? indexedLabel : label}
    </Button>
  )
}

function PublishedSwitch({ entry, disabled }: { entry: FolderEntry; disabled: boolean }) {
  const { t } = useTranslation()
  const exclusion = useExclusion()
  const publicationId = entry.publication_id ?? ''
  return (
    <span className="flex shrink-0 items-center gap-2">
      <span className="hidden text-xs-plus text-muted-foreground sm:inline">
        {t(entry.published ? 'admin.folders.sub.on' : 'admin.folders.sub.off')}
      </span>
      <Toggle
        checked={entry.published}
        disabled={disabled || exclusion.isPending}
        label={t('admin.folders.sub.label', { name: entry.name })}
        onChange={(published) => {
          exclusion.mutate({ publicationId, path: entry.relative_path, published })
        }}
      />
    </span>
  )
}

/** How many folders below the library the path spells out; the dialog is narrow everywhere. */
const SHOWN_STEPS = 2

const STEP = 'shrink-0 whitespace-nowrap rounded px-1.5 py-0.5'

/**
 * Where the picker stands: the library, then the last two folders. Deeper than that, everything
 * in between folds into one "…" that leads to the folder above the two, so the path keeps to one
 * line - the same way the album path does on a phone.
 */
function FolderPath({
  root,
  segments,
  onGo,
}: {
  root: string
  segments: string[]
  onGo: (path: string) => void
}) {
  const { t } = useTranslation()
  const hidden = Math.max(0, segments.length - SHOWN_STEPS)
  const pathTo = (depth: number) => segments.slice(0, depth).join('/')

  return (
    <nav
      aria-label={t('admin.folders.add.path')}
      className="-ml-1.5 flex min-w-0 flex-nowrap items-center gap-1 text-base text-muted-foreground"
    >
      {segments.length === 0 ? (
        <span className={cn(STEP, 'text-foreground')}>{root}</span>
      ) : (
        <GoButton
          label={root}
          onClick={() => {
            onGo('')
          }}
        />
      )}
      {hidden > 0 && (
        <>
          <Chevron />
          <GoButton
            label="…"
            ariaLabel={t('admin.folders.add.pathFolded', { name: segments[hidden - 1] })}
            onClick={() => {
              onGo(pathTo(hidden))
            }}
          />
        </>
      )}
      {segments.slice(hidden).map((segment, index) => {
        const depth = hidden + index + 1
        const last = depth === segments.length
        return (
          <span
            key={depth}
            className={cn('flex items-center gap-1', last ? 'min-w-0' : 'shrink-0')}
          >
            <Chevron />
            {last ? (
              <span className="min-w-0 truncate px-1.5 py-0.5 text-foreground" title={segment}>
                {segment}
              </span>
            ) : (
              <GoButton
                label={segment}
                onClick={() => {
                  onGo(pathTo(depth))
                }}
              />
            )}
          </span>
        )
      })}
    </nav>
  )
}

function GoButton({
  label,
  ariaLabel,
  onClick,
}: {
  label: string
  ariaLabel?: string | undefined
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      className={cn(STEP, 'hover:bg-secondary hover:text-foreground')}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

function Chevron() {
  return <Symbol name="chevron_right" size={16} className="shrink-0 text-muted-foreground/60" />
}

export function FolderPicker({
  enabled,
  onChoose,
  chooseLabel,
  initialPath = '',
}: {
  enabled: boolean
  onChoose: (entry: FolderEntry) => void
  chooseLabel: string
  /** Where the walk starts: the library, or inside a published folder. */
  initialPath?: string
}) {
  const { t } = useTranslation()
  const [path, setPath] = useState(initialPath)
  const folders = useFolders(path, enabled)

  const segments = path ? path.split('/') : []

  return (
    <div className="space-y-3">
      <FolderPath
        root={folders.data?.library_path ?? t('admin.folders.add.root')}
        segments={segments}
        onGo={setPath}
      />

      {/* Pictures often lie in the mounted share itself, so it is offered like any other. */}
      {folders.data && (
        <div className="flex items-center gap-2 rounded-lg border border-hairline/10 bg-secondary/40 p-2">
          <Symbol name="folder" size={20} filled className="shrink-0 text-primary" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-md text-foreground">
              {folders.data.current.name || folders.data.library_path}
            </span>
            <span className="block truncate text-xs-plus text-muted-foreground">
              {t('admin.folders.add.mediaHere', { count: folders.data.current.media_files ?? 0 })}
            </span>
          </span>
          <ChooseButton
            entry={folders.data.current}
            label={chooseLabel}
            indexedLabel={t('admin.folders.add.alreadyPublished')}
            onChoose={onChoose}
          />
        </div>
      )}

      {folders.isPending && (
        <p className="text-base text-muted-foreground">{t('admin.folders.loading')}</p>
      )}
      {folders.isError && (
        <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
      )}
      {folders.data?.items.length === 0 && (
        <p className="text-base text-muted-foreground">{t('admin.folders.add.noSubfolders')}</p>
      )}

      <ul className="max-h-[320px] overflow-y-auto">
        {folders.data?.items.map((entry) => (
          <li
            key={entry.path}
            className="flex items-center gap-2 border-b border-hairline/[0.06] py-2 last:border-b-0"
          >
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-1 text-left hover:bg-secondary/50"
              onClick={() => {
                setPath(entry.relative_path)
              }}
            >
              <Symbol
                name="folder"
                size={20}
                filled={entry.is_mount}
                className={
                  entry.is_mount ? 'shrink-0 text-primary' : 'shrink-0 text-muted-foreground'
                }
              />
              <span className="min-w-0">
                <span className="block truncate text-md text-foreground">{entry.name}</span>
                <span className="block truncate text-xs-plus text-muted-foreground">
                  {entry.excluded
                    ? t('admin.folders.sub.excluded')
                    : entry.published
                      ? t('admin.folders.add.alreadyPublished')
                      : entry.is_mount
                        ? t('admin.folders.add.mounted')
                        : t('admin.folders.add.open')}
                </span>
              </span>
            </button>

            <ChooseButton
              entry={entry}
              label={chooseLabel}
              indexedLabel={t('admin.folders.add.alreadyPublished')}
              onChoose={onChoose}
              insideExcluded={folders.data.current.excluded}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}
