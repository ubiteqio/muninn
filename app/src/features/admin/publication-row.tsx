import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError } from '@/api/problem'
import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { FolderPicker } from '@/features/admin/folder-picker'
import {
  type Publication,
  type ScanStatus,
  usePublish,
  useStartSync,
  useUnpublish,
  useUpdatePublication,
} from '@/features/admin/use-library'
import { FormError } from '@/features/auth/form-error'
import { cn } from '@/lib/utils'

const STATUS_STYLE: Record<ScanStatus, { icon: string; className: string }> = {
  never: { icon: 'history', className: 'text-muted-foreground' },
  running: { icon: 'sync', className: 'text-accent' },
  ok: { icon: 'check_circle', className: 'text-primary' },
  paused: { icon: 'warning', className: 'text-accent' },
  unavailable: { icon: 'error', className: 'text-destructive' },
  failed: { icon: 'error', className: 'text-destructive' },
  cancelled: { icon: 'block', className: 'text-muted-foreground' },
}

/** One published folder: where it is, how its last read went, and what can be done with it. */
export function PublicationRow({ publication }: { publication: Publication }) {
  const { t } = useTranslation()
  const startSync = useStartSync()
  const update = useUpdatePublication()
  const unpublish = useUnpublish()

  const [error, setError] = useState<string | null>(null)

  const status = STATUS_STYLE[publication.last_sync_status]
  const busy = startSync.isPending || update.isPending || unpublish.isPending

  async function run(action: Promise<unknown>) {
    setError(null)
    try {
      await action
    } catch (failure) {
      setError(messageFor(failure, t))
    }
  }

  return (
    <li className="space-y-3 border-b border-hairline/[0.06] p-4 last:border-b-0">
      <div className="flex items-start gap-3">
        <Symbol
          name="folder"
          size={22}
          filled
          className={cn(
            'mt-0.5 shrink-0',
            publication.enabled ? 'text-primary' : 'text-muted-foreground',
          )}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-md font-semibold text-foreground">
            {publication.name || t('admin.folders.library')}
          </p>
          <p className="truncate font-mono text-xs-plus text-muted-foreground">
            {publication.relative_path || '/'}
          </p>
          <p className={cn('mt-1 flex items-center gap-1.5 text-xs-plus', status.className)}>
            <Symbol name={status.icon} size={16} />
            {t(`admin.folders.status.${publication.last_sync_status}`)}
            {publication.last_sync_at && (
              <span className="text-muted-foreground">
                · {new Date(publication.last_sync_at).toLocaleString('de-DE')}
              </span>
            )}
            {!publication.enabled && (
              <span className="text-muted-foreground">· {t('admin.folders.paused')}</span>
            )}
          </p>
        </div>
      </div>

      {publication.progress && (
        <div className="space-y-1.5">
          <p className="flex flex-wrap items-center gap-x-2 text-xs-plus text-muted-foreground">
            <span>
              {t('admin.folders.progress.files', {
                done: publication.progress.files_done,
                total: publication.progress.files_total,
              })}
            </span>
            {publication.progress.current && (
              <>
                <span>·</span>
                <span className="truncate font-mono">{publication.progress.current}</span>
              </>
            )}
          </p>
          <div
            className="h-1 w-full overflow-hidden rounded-full bg-secondary"
            role="progressbar"
            aria-valuenow={publication.progress.files_done}
            aria-valuemin={0}
            aria-valuemax={publication.progress.files_total}
            aria-label={t('admin.folders.progress.label')}
          >
            <div
              className="h-full bg-primary transition-[width]"
              style={{
                width: `${String(
                  Math.round(
                    (publication.progress.files_done /
                      Math.max(publication.progress.files_total, 1)) *
                      100,
                  ),
                )}%`,
              }}
            />
          </div>
        </div>
      )}

      {publication.waiting_files > 0 && (
        // "Read" must never mean "nothing to see": files that are still being copied are only
        // taken once a second listing agrees, and that look is already queued.
        <p className="flex items-start gap-2 rounded-md border border-hairline/10 bg-secondary/40 px-3 py-2 text-base text-muted-foreground">
          <Symbol name="history" size={18} className="mt-px shrink-0" />
          {t('admin.folders.waiting', { count: publication.waiting_files })}
        </p>
      )}

      {/* A paused folder says so in its status line and in the confirmation; the server's
          sentence for it would only repeat that, in English. */}
      {publication.last_sync_message && publication.last_sync_status !== 'paused' && (
        <p className="rounded-md border border-hairline/10 bg-secondary/40 px-3 py-2 text-base text-muted-foreground">
          {publication.last_sync_message}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => void run(startSync.mutateAsync({ id: publication.id }))}
        >
          <Symbol name="sync" size={20} />
          {t('admin.folders.action.scan')}
        </Button>

        {publication.pending_deletions > 0 && (
          <ConfirmDialog
            trigger={
              <Button disabled={busy}>
                <Symbol name="warning" size={20} />
                {t('admin.folders.action.confirm', { count: publication.pending_deletions })}
              </Button>
            }
            title={t('admin.folders.confirmDeletions.title', {
              count: publication.pending_deletions,
            })}
            description={t('admin.folders.confirmDeletions.description')}
            confirmLabel={t('admin.folders.confirmDeletions.confirm')}
            cancelLabel={t('admin.folders.action.cancel')}
            closeLabel={t('common.close')}
            destructive
            pending={busy}
            onConfirm={() =>
              run(startSync.mutateAsync({ id: publication.id, confirm_deletions: true }))
            }
          />
        )}

        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            void run(update.mutateAsync({ id: publication.id, enabled: !publication.enabled }))
          }
        >
          <Symbol name={publication.enabled ? 'block' : 'check_circle'} size={20} />
          {t(publication.enabled ? 'admin.folders.action.pause' : 'admin.folders.action.resume')}
        </Button>

        <SubfoldersDialog publication={publication} />

        <ConfirmDialog
          trigger={
            <Button variant="outline" disabled={busy}>
              <Symbol name="delete" size={20} />
              {t('admin.folders.action.remove')}
            </Button>
          }
          title={t('admin.folders.remove.title', {
            name: publication.name || t('admin.folders.library'),
          })}
          description={t('admin.folders.removeHint')}
          confirmLabel={t('admin.folders.action.removeConfirm')}
          cancelLabel={t('admin.folders.action.cancel')}
          closeLabel={t('common.close')}
          destructive
          pending={busy}
          onConfirm={() => run(unpublish.mutateAsync(publication.id))}
        />
      </div>

      <FormError message={error} />
    </li>
  )
}

/**
 * The published folder, opened: every subfolder with a switch, to leave single ones out again
 * without taking the whole folder back.
 */
function SubfoldersDialog({ publication }: { publication: Publication }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const publish = usePublish()
  const name = publication.name || t('admin.folders.library')

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Symbol name="folder" size={20} />
          {t('admin.folders.sub.action')}
        </Button>
      </DialogTrigger>
      <DialogContent closeLabel={t('common.close')} className="max-w-2xl">
        <DialogTitle>{t('admin.folders.sub.title', { name })}</DialogTitle>
        <DialogDescription>{t('admin.folders.sub.description')}</DialogDescription>
        <div className="mt-4">
          <FolderPicker
            enabled={open}
            initialPath={publication.relative_path}
            chooseLabel={t('admin.folders.add.choose')}
            onChoose={(entry) => {
              publish.mutate(entry.relative_path)
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}

function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')
  if (failure.is('worker-unreachable')) return t('admin.folders.error.noWorker')
  return failure.problem.detail ?? t('auth.error.unexpected')
}
