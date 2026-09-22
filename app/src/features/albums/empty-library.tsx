import { useTranslation } from 'react-i18next'

import { Knotwork } from '@/components/muninn/knotwork'
import { Symbol } from '@/components/muninn/symbol'

/**
 * What the albums look like before there are any.
 *
 * It says what belongs here and shows the shape of it, and it stops there: publishing a folder
 * is an admin's job and lives in the admin area. A button here would be a dead end for everybody
 * else, and for an admin it would put a piece of the machine room on a screen that belongs to
 * looking at pictures.
 */
export function EmptyLibrary() {
  const { t } = useTranslation()

  return (
    <div className="flex min-h-[55vh] flex-col items-center justify-center px-6 text-center">
      <AlbumStack />

      <h2 className="mt-8 text-title font-semibold text-foreground">
        {t('albums.emptyLibrary.title')}
      </h2>
      <p className="mt-2 max-w-[420px] text-md leading-relaxed text-muted-foreground">
        {t('albums.emptyLibrary.body')}
      </p>

      <Knotwork className="mt-9 w-28" />
    </div>
  )
}

/**
 * Three album tiles as they will stand here once a folder is published: the shape of the thing
 * that is missing, which says more than any icon of an empty box.
 */
function AlbumStack() {
  return (
    <div aria-hidden="true" className="relative h-[116px] w-[210px]">
      <span className="absolute left-0 top-4 h-[88px] w-[88px] -rotate-6 rounded-xl border border-hairline/10 bg-secondary/40" />
      <span className="absolute right-0 top-4 h-[88px] w-[88px] rotate-6 rounded-xl border border-hairline/10 bg-secondary/40" />
      <span className="absolute left-1/2 top-0 flex h-[104px] w-[104px] -translate-x-1/2 items-center justify-center rounded-xl border border-primary/25 bg-card">
        <Symbol name="photo_library" size={34} className="text-primary/70" />
      </span>
    </div>
  )
}

/** An album that exists but holds nothing yet - a folder on the NAS that is empty. */
export function EmptyAlbum() {
  const { t } = useTranslation()

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center px-6 text-center">
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-secondary/50">
        <Symbol name="folder" size={28} className="text-muted-foreground" />
      </span>
      <h2 className="mt-5 text-lg font-semibold text-foreground">{t('albums.emptyAlbum.title')}</h2>
      <p className="mt-2 max-w-[400px] text-base leading-relaxed text-muted-foreground">
        {t('albums.emptyAlbum.body')}
      </p>
    </div>
  )
}
