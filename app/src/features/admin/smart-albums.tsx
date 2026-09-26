import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useRebuildSmarts, useSmartsState } from '@/features/admin/use-smarts'

/** As many as fill a screen. The field starts here and remembers nothing: it is one press. */
const DEFAULT_WANTED = 21
const MOST = 500

/**
 * Building the Smarts by hand.
 *
 * They are found nightly, and only for albums that changed - so an admin who has just published
 * a folder, or who has changed nothing but wants to see what the pictures fall into, would have
 * to wait for three in the morning. This does it now, for as many chapters as are asked for:
 * the albums without chapters first, then those whose chapters are oldest, so pressing again
 * carries on rather than doing the same albums over.
 */
export function SmartAlbums() {
  const { t } = useTranslation()
  const state = useSmartsState()
  const rebuild = useRebuildSmarts()
  const [wanted, setWanted] = useState(String(DEFAULT_WANTED))

  const asked = Number(wanted)
  const usable = Number.isInteger(asked) && asked >= 1 && asked <= MOST

  return (
    <section aria-label={t('admin.smarts.title')}>
      <SectionHeading title={t('admin.smarts.title')} />
      <Card className="mt-3 space-y-4 p-5">
        <p className="text-base text-muted-foreground">{t('admin.smarts.description')}</p>

        {state.data && (
          <p className="text-xs-plus text-muted-foreground">
            {t('admin.smarts.holds', {
              chapters: state.data.chapters,
              albums: state.data.albums,
              media: state.data.media,
            })}
            {state.data.outstanding > 0 &&
              ` · ${t('admin.smarts.outstanding', { count: state.data.outstanding })}`}
          </p>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs-plus font-medium text-foreground">
              {t('admin.smarts.wanted')}
            </span>
            <Input
              type="number"
              min={1}
              max={MOST}
              inputMode="numeric"
              value={wanted}
              className="w-24"
              onChange={(event) => {
                setWanted(event.target.value)
              }}
            />
          </label>
          <Button
            disabled={!usable || rebuild.isPending}
            onClick={() => {
              rebuild.mutate(asked)
            }}
          >
            <Symbol
              name="auto_awesome"
              size={18}
              {...(rebuild.isPending && { className: 'animate-pulse' })}
            />
            {rebuild.isPending ? t('admin.smarts.building') : t('admin.smarts.build')}
          </Button>
        </div>

        {/* It runs while the request is open, so what comes back is what was built - and a
            library that has nothing left to build says that instead of a bare zero. */}
        {rebuild.data && (
          <p role="status" className="flex items-start gap-2 text-base text-foreground">
            <Symbol name="check_circle" size={18} className="mt-0.5 text-primary" />
            <span>
              {rebuild.data.albums === 0
                ? t('admin.smarts.nothingLeft')
                : t('admin.smarts.built', {
                    chapters: rebuild.data.chapters,
                    albums: rebuild.data.albums,
                  })}
            </span>
          </p>
        )}
        {rebuild.isError && (
          <p role="status" className="text-base text-destructive">
            {t('auth.error.unreachable')}
          </p>
        )}
      </Card>
    </section>
  )
}
