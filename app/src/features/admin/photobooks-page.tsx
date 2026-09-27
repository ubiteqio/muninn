import { type ComponentProps, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import { Field } from '@/features/auth/field'
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
  const [maxMedia, setMaxMedia] = useState('150')
  const [count, setCount] = useState('1')
  const [title, setTitle] = useState('')

  const books = shelf.data?.items ?? []

  return (
    <AdminArea section="photobooks">
      <div className="space-y-5">
        <Card className="p-5">
          <h2 className="text-lg font-semibold text-foreground">{t('admin.photobooks.title')}</h2>
          <p className="mt-1.5 text-base text-muted-foreground">
            {t('admin.photobooks.description')}
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Choice
              label={t('admin.photobooks.album')}
              hint={t('admin.photobooks.albumHint')}
              value={albumId}
              onChange={(event) => {
                setAlbumId(event.target.value)
              }}
            >
              <option value="">{t('admin.photobooks.chooseAlbum')}</option>
              {(albums.data ?? []).map((album) => (
                <option key={album.id} value={album.id}>
                  {album.relative_path} ({album.media_count})
                </option>
              ))}
            </Choice>

            <Choice
              label={t('admin.photobooks.size')}
              hint={t('admin.photobooks.sizeHint')}
              value={size}
              onChange={(event) => {
                setSize(event.target.value as (typeof SIZES)[number])
              }}
            >
              {SIZES.map((one) => (
                <option key={one} value={one}>
                  {t(`admin.photobooks.${one}`)}
                </option>
              ))}
            </Choice>

            <Field
              label={t('admin.photobooks.maxMedia')}
              hint={t('admin.photobooks.maxMediaHint')}
              type="number"
              inputMode="numeric"
              min={4}
              max={400}
              value={maxMedia}
              onChange={(event) => {
                setMaxMedia(event.target.value)
              }}
            />

            <Field
              label={t('admin.photobooks.count')}
              hint={t('admin.photobooks.countHint')}
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={count}
              onChange={(event) => {
                setCount(event.target.value)
              }}
            />

            <Field
              label={t('admin.photobooks.bookTitle')}
              hint={t('admin.photobooks.titleHint')}
              value={title}
              onChange={(event) => {
                setTitle(event.target.value)
              }}
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              type="button"
              disabled={albumId === '' || make.isPending}
              onClick={() => {
                make.mutate({
                  album_id: albumId,
                  size,
                  style: 'scrapbook',
                  max_media: Number(maxMedia),
                  count: Number(count),
                  title,
                })
              }}
            >
              <Symbol name="menu_book" size={20} />
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
        </Card>

        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-foreground">
            {t('admin.photobooks.existing')}
          </h2>
          {books.length === 0 ? (
            <Card className="p-5 text-base text-muted-foreground">
              {t('admin.photobooks.nothing')}
            </Card>
          ) : (
            books.map((book) => <BookRow key={book.id} book={book} />)
          )}
        </div>
      </div>
    </AdminArea>
  )
}

/** A labelled select, in the shape of the labelled inputs beside it. */
function Choice({
  label,
  hint,
  children,
  ...props
}: { label: string; hint?: string } & ComponentProps<'select'>) {
  const id = useId()
  const hintId = `${id}-hint`

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        aria-describedby={hint ? hintId : undefined}
        className="h-11 w-full rounded-lg border border-hairline/10 bg-card px-3 text-md text-foreground focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
        {...props}
      >
        {children}
      </select>
      {hint && (
        <p id={hintId} className="text-xs-plus text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
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
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {book.cover ? (
            <img src={book.cover} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
          ) : (
            <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-secondary/60 text-muted-foreground">
              <Symbol name="menu_book" size={20} />
            </span>
          )}
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-base font-semibold text-foreground">
              {book.title}
              {book.state !== 'ready' && (
                <span className="rounded-badge bg-primary/[0.14] px-1.5 py-0.5 text-3xs font-medium tracking-section uppercase text-primary">
                  {t(book.state === 'failed' ? 'photobooks.failed' : 'photobooks.building')}
                </span>
              )}
            </p>
            <p className="mt-0.5 truncate text-xs-plus text-muted-foreground">
              {book.album}
              {book.subtitle ? ` · ${book.subtitle}` : ''}
            </p>
            <p className="mt-0.5 text-xs-plus text-muted-foreground">{note}</p>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            className="h-8 px-2 text-xs-plus"
            disabled={rebuild.isPending}
            onClick={() => {
              rebuild.mutate(book.id)
            }}
          >
            <Symbol name="sync" size={16} />
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
        </div>
      </div>
    </Card>
  )
}
