import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError } from '@/api/problem'
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
import { usePublish } from '@/features/admin/use-library'
import { FormError } from '@/features/auth/form-error'

/**
 * Choosing which folder appears under Albums.
 *
 * No name is asked for: the album is called what the folder is called, and it appears where the
 * folder is - that is the whole point. A title of its own can be given later in the album.
 */
export function AddFolderDialog() {
  const { t } = useTranslation()
  const publish = usePublish()

  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        setError(null)
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Symbol name="create_new_folder" size={20} />
          {t('admin.folders.add.action')}
        </Button>
      </DialogTrigger>

      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('admin.folders.add.title')}</DialogTitle>
        <DialogDescription>{t('admin.folders.add.description')}</DialogDescription>

        <div className="mt-4">
          <FolderPicker
            enabled={open}
            chooseLabel={t('admin.folders.add.choose')}
            onChoose={(entry) => {
              setError(null)
              publish.mutate(entry.relative_path, {
                onSuccess: () => {
                  setOpen(false)
                },
                onError: (failure) => {
                  setError(messageFor(failure, t))
                },
              })
            }}
          />
        </div>

        <div className="mt-3">
          <FormError message={error} />
        </div>
      </DialogContent>
    </Dialog>
  )
}

function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')
  if (failure.is('already-published')) return t('admin.folders.error.alreadyPublished')
  if (failure.is('path-not-allowed')) return t('admin.folders.error.notAllowed')
  return failure.problem.detail ?? t('auth.error.unexpected')
}
