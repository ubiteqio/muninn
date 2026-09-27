import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AdminArea } from '@/features/admin/admin-area'
import {
  type Photobook,
  useMakePhotobooks,
  usePhotobooks,
  usePhotobookUpdates,
  usePublishedAlbums,
  useRebuildPhotobook,
  useRemovePhotobook,
} from '@/features/photobooks/use-photobooks'

const SIZES = ['small', 'medium', 'large'] as const

/**
 * Fotobücher in the admin area: making them, and taking them off the shelf.
 *
 * An album becomes a book here and nowhere else. The two numbers decide how big it is - a share
 * of the album, and a ceiling above it - because a folder of 4500 holidays would otherwise make
 * a book nobody finishes. The building itself happens in the worker, so this page hands over
 * and the shelf fills by itself a few minutes later.
 */
export function PhotobooksPage() {
  const { t } = useTranslation()
  const albums = usePublishedAlbums()
  const shelf = usePhotobooks()
  const make = useMakePhotobooks()
  usePhotobookUpdates()

  const [albumId, setAlbumId] = useState('')
  const [size, setSize] = useState<(typeof SIZES)[number]>('medium')
  const [maxMedia, setMaxMedia] = useState(150)
  const [count, setCount] = useState(1)
  const [title, setTitle] = useState('')

  const books = shelf.data?.items ?? []

  return (
    <AdminArea section="photobooks">
      <section className="space-y-4 rounded-xl border border-hairline/10 bg-secondary/40 p-4">
        <div>
          <h2 className="text-lg font-semibold">{t('admin.photobooks.title')}</h2>
          <p className="text-base text-muted-foreground">{t('admin.photobooks.description')}</p>
        </div>

        <label className="block space-y-1">
          <span className="text-xs-plus font-medium">{t('admin.photobooks.album')}</span>
          <select
            value={albumId}
            onChange={(event) => {
              setAlbumId(event.target.value)
            }}
            className="h-10 w-full rounded-lg border border-hairline/20 bg-background px-3 text-base"
          >
            <option value="">{t('admin.photobooks.chooseAlbum')}</option>
            {(albums.data ?? []).map((album) => (
              <option key={album.id} value={album.id}>
                {album.relative_path} ({album.media_count})
              </option>
            ))}
          </select>
          <span className="text-2xs text-muted-foreground">{t('admin.photobooks.albumHint')}</span>
        </label>

        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block space-y-1">
            <span className="text-xs-plus font-medium">{t('admin.photobooks.size')}</span>
            <select
              value={size}
              onChange={(event) => {
                setSize(event.target.value as (typeof SIZES)[number])
              }}
              className="h-10 w-full rounded-lg border border-hairline/20 bg-background px-3 text-base"
            >
              {SIZES.map((one) => (
                <option key={one} value={one}>
                  {t(`admin.photobooks.${one}`)}
                </option>
              ))}
            </select>
            <span className="text-2xs text-muted-foreground">{t('admin.photobooks.sizeHint')}</span>
          </label>

          <label className="block space-y-1">
            <span className="text-xs-plus font-medium">{t('admin.photobooks.maxMedia')}</span>
            <Input
              type="number"
              min={4}
              max={400}
              value={maxMedia}
              onChange={(event) => {
                setMaxMedia(Number(event.target.value))
              }}
            />
            <span className="text-2xs text-muted-foreground">
              {t('admin.photobooks.maxMediaHint')}
            </span>
          </label>

          <label className="block space-y-1">
            <span className="text-xs-plus font-medium">{t('admin.photobooks.count')}</span>
            <Input
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={(event) => {
                setCount(Number(event.target.value))
              }}
            />
            <span className="text-2xs text-muted-foreground">{t('admin.photobooks.countHint')}</span>
          </label>
        </div>

        <label className="block space-y-1">
          <span className="text-xs-plus font-medium">{t('admin.photobooks.bookTitle')}</span>
          <Input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value)
            }}
            placeholder={t('admin.photobooks.titleHint')}
          />
        </label>

        <div className="flex items-center gap-3">
          <Button
            type="button"
            disabled={albumId === '' || make.isPending}
            onClick={() => {
              make.mutate({
                album_id: albumId,
                size,
                style: 'scrapbook',
                max_media: maxMedia,
                count,
                title,
              })
            }}
          >
            <Symbol name="menu_book" size={18} className="mr-1.5" />
            {t(make.isPending ? 'admin.photobooks.making' : 'admin.photobooks.make')}
          </Button>
          {albumId === '' && (
            <span className="text-xs-plus text-muted-foreground">
              {t('admin.photobooks.needsAlbum')}
            </span>
          )}
          {make.isSuccess && (
            <span className="text-xs-plus text-muted-foreground">
              {t('admin.photobooks.made', { count: make.data.items.length })}
            </span>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">{t('admin.photobooks.existing')}</h2>
        {books.length === 0 ? (
          <p className="text-base text-muted-foreground">{t('admin.photobooks.nothing')}</p>
        ) : (
          <ul className="space-y-2">
            {books.map((book) => (
              <BookRow key={book.id} book={book} />
            ))}
          </ul>
        )}
      </section>
    </AdminArea>
  )
}

function BookRow({ book }: { book: Photobook }) {
  const { t } = useTranslation()
  const remove = useRemovePhotobook()
  const rebuild = useRebuildPhotobook()

  const note =
    book.state === 'ready'
      ? [
          t('admin.photobooks.pagesAndMedia', { pages: book.pages, media: book.media }),
          book.written ? t('admin.photobooks.written') : t('admin.photobooks.plain'),
        ].join(' · ')
      : book.state === 'failed'
        ? book.trouble || t('photobooks.failed')
        : t('photobooks.building')

  return (
    <li className="flex items-center gap-3 rounded-xl border border-hairline/10 bg-secondary/40 p-3">
      {book.cover ? (
        <img src={book.cover} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
      ) : (
        <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
          <Symbol name="menu_book" size={20} />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-base font-medium">{book.title}</p>
        <p className="truncate text-xs-plus text-muted-foreground">
          {book.album}
          {book.subtitle ? ` · ${book.subtitle}` : ''}
        </p>
        <p className="truncate text-2xs text-muted-foreground">{note}</p>
      </div>
      <Button
        variant="outline"
        className="h-8 px-2 text-xs-plus"
        disabled={rebuild.isPending}
        onClick={() => {
          rebuild.mutate(book.id)
        }}
      >
        {t('admin.photobooks.rebuild')}
      </Button>
      <ConfirmDialog
        trigger={
          <Button
            variant="outline"
            aria-label={t('admin.photobooks.remove')}
            className="h-8 px-2 text-xs-plus"
            disabled={remove.isPending}
          >
            <Symbol name="delete" size={16} />
          </Button>
        }
        title={t('admin.photobooks.removeTitle')}
        description={t('admin.photobooks.removeBody', { title: book.title })}
        confirmLabel={t('admin.photobooks.remove')}
        cancelLabel={t('common.cancel')}
        closeLabel={t('common.close')}
        destructive
        pending={remove.isPending}
        onConfirm={() => {
          remove.mutate(book.id)
        }}
      />
    </li>
  )
}
