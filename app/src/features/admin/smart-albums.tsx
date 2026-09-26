import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { useRebuildSmarts, useSmartsState } from '@/features/admin/use-smarts'

/**
 * Building the Smarts by hand: the block under the two numbers that say how many there are and
 * how much each one holds.
 *
 * They are found every night, so this is for an admin who has just published a folder, or has
 * just changed one of the numbers and wants to see what comes of it rather than wait for half
 * past three. It takes the numbers as they are saved, which is why it asks for nothing itself.
 */
export function SmartAlbums() {
  const { t } = useTranslation()
  const state = useSmartsState()
  const rebuild = useRebuildSmarts()

  return (
    <div className="mt-4 space-y-4 border-t border-hairline/10 pt-4">
      <p className="text-base text-muted-foreground">{t('admin.smarts.description')}</p>

      {state.data && state.data.chapters > 0 && (
        <p className="text-xs-plus text-muted-foreground">
          {t('admin.smarts.holds', {
            chapters: state.data.chapters,
            media: state.data.media,
          })}
          {' · '}
          {Object.entries(state.data.by_kind)
            .sort(([, first], [, second]) => second - first)
            .map(([kind, count]) => `${count} ${t(`smarts.kind.${kind}`)}`)
            .join(', ')}
        </p>
      )}

      <Button
        type="button"
        disabled={rebuild.isPending}
        onClick={() => {
          rebuild.mutate()
        }}
      >
        <Symbol
          name="auto_awesome"
          size={18}
          {...(rebuild.isPending && { className: 'animate-pulse' })}
        />
        {rebuild.isPending ? t('admin.smarts.building') : t('admin.smarts.build')}
      </Button>

      {/* It runs while the request is open, so what comes back is what was built. */}
      {rebuild.data && (
        <p role="status" className="flex items-start gap-2 text-base text-foreground">
          <Symbol name="check_circle" size={18} className="mt-0.5 text-primary" />
          <span>
            {t('admin.smarts.built', {
              chapters: rebuild.data.chapters,
              media: rebuild.data.media,
            })}
          </span>
        </p>
      )}
      {rebuild.isError && (
        <p role="status" className="text-base text-destructive">
          {t('auth.error.unreachable')}
        </p>
      )}
    </div>
  )
}
