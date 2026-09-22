import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { Card } from '@/components/ui/card'
import { AddFolderDialog } from '@/features/admin/add-folder-dialog'
import { AdminArea } from '@/features/admin/admin-area'
import { PublicationRow } from '@/features/admin/publication-row'
import { useIndexStatus } from '@/features/admin/use-library'

/**
 * The folders Muninn indexes. This is where an album comes from: a folder on the NAS is picked
 * here, and everything below it becomes albums - the originals are never touched.
 */
/** When the clock reads everything again, in words rather than as a timestamp. */
function nextSyncHint(nextSyncAt: string | null, t: TFunction): string {
  if (!nextSyncAt) return t('admin.folders.nextUnknown')

  const minutes = Math.round((new Date(nextSyncAt).getTime() - Date.now()) / 60_000)
  if (minutes <= 0) return t('admin.folders.nextNow')
  return t('admin.folders.next', { count: minutes })
}

export function AdminFoldersPage() {
  const { t } = useTranslation()
  const { data, isPending, isError } = useIndexStatus()

  const counts: { key: string; value: number }[] = data
    ? [
        { key: 'albums', value: data.albums },
        { key: 'media', value: data.media },
        { key: 'missing', value: data.missing },
        { key: 'pending', value: data.pending_metadata + data.pending_derivatives },
      ]
    : []

  return (
    <AdminArea section="folders">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t('admin.folders.title')}</h2>
          <p className="mt-1.5 text-base text-muted-foreground">{t('admin.folders.description')}</p>
          {data && (
            <p className="mt-1 text-xs-plus text-muted-foreground">
              {t('admin.folders.mountHint', { path: data.library_path })}{' '}
              {nextSyncHint(data.next_sync_at, t)}
            </p>
          )}
        </div>
        <AddFolderDialog />
      </div>

      {isPending && <p className="text-base text-muted-foreground">{t('admin.folders.loading')}</p>}
      {isError && <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>}

      {data && (
        <Card className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-4">
          {counts.map(({ key, value }) => (
            <div key={key}>
              <p className="text-title font-semibold text-foreground">
                {value.toLocaleString('de-DE')}
              </p>
              <p className="text-xs-plus text-muted-foreground">
                {t(`admin.folders.count.${key}`)}
              </p>
            </div>
          ))}
        </Card>
      )}

      {data?.publications.length === 0 && (
        <p className="text-base text-muted-foreground">{t('admin.folders.empty')}</p>
      )}

      {data && data.publications.length > 0 && (
        <Card className="overflow-hidden">
          <ul>
            {data.publications.map((publication) => (
              <PublicationRow key={publication.id} publication={publication} />
            ))}
          </ul>
        </Card>
      )}
    </AdminArea>
  )
}
